from __future__ import annotations


__all__ = ['Router']


from collections.abc import Generator, AsyncGenerator

from typing_extensions import TYPE_CHECKING, Any, Self, Type, TypeVar

from eventry.config import DispatcherConfig
from eventry.loggers import router_logger
from eventry.exceptions import FinalizingError, _EarlyFinalized
from eventry.asyncio.handler_manager import HandlerManager
from eventry.asyncio.callable_wrappers import Handler
from eventry.asyncio.middleware_manager import (
    MiddlewaresExecutor,
    MiddlewareManagerTypes,
    MiddlewareWrappedCallable,
)


if TYPE_CHECKING:
    from eventry.asyncio.event import Event


HandlerManagerT = TypeVar('HandlerManagerT', bound=HandlerManager[Any, Any, Any, Any])


class Router:
    def __init__(self, name: str):
        self._name = name
        self._parent: Self | None = None
        self._sub_routers: dict[str, Self] = {}
        self._handler_managers: dict[str, HandlerManager[Any, Any, Any, Self]] = {}
        self._default_handler_manager: HandlerManager[Any, Any, Any, Self] | None = None

    def set_default_handler_manager(self, manager: HandlerManager[Any, Any, Any, Self]):
        if self._default_handler_manager is not None:
            raise RuntimeError('Default handler manager already set.')

        self._default_handler_manager = manager
        self._handler_managers[manager.name] = manager

    def get_handler(self, handler_id: str, /) -> Handler[Any] | None:
        for manager in self._handler_managers.values():
            if handler_id in manager.handlers:
                return manager.handlers[handler_id]

        for router in self._sub_routers.values():
            result = router.get_handler(handler_id)
            if result is not None:
                return result
        return None

    def _add_handler_manager(self, handler_manager: HandlerManagerT, /) -> HandlerManagerT:
        # if not handler_manager.event_filter:
        #     raise ValueError(
        #         'Cannot add handler manager without event type filter. '
        #         'Assign it as default handler manager.',
        #     )
        # todo: warning

        if handler_manager.name in self._handler_managers:
            raise ValueError(
                f'Manager with name {handler_manager.name!r} already added to router {self._name!r}. ',
            )

        self._handler_managers[handler_manager.name] = handler_manager
        return handler_manager

    def get_handler_manager(self, event: Event, /) -> HandlerManager[Any, Any, Any, Self] | None:
        for i in self._handler_managers.values():
            if i is not self._default_handler_manager and i.check_event(event):
                return i

        if self._default_handler_manager:
            return self._default_handler_manager

        return None

    def connect_router(self, router: Router) -> None:
        router.parent_router = self

    def connect_routers(self, *routers: Router) -> None:
        for i in routers:
            i.parent_router = self

    def __getitem__(self, item: Event) -> HandlerManager[Any, Any, Any, Self] | None:
        return self.get_handler_manager(item)

    async def propagate_event(
        self,
        config: DispatcherConfig,
        event: Event,
        event_context: dict[str, Any],
        silent: bool = False,
    ) -> AsyncGenerator[Exception, None]:
        """
        :raises FinalizingError: If an error occurred during finalizing manager-level middlewares.
        """
        router_logger.debug('Event %s entering router %s.', id(event), self.name)
        manager = self[event]
        manager_middlewares_executor = None

        if manager is not None:
            router_logger.debug(
                'Found suitable handler manager for event %s: %s.',
                id(event),
                manager.name
            )
            manager_middlewares_executor = MiddlewaresExecutor()
            async for i in self._inner_propagate_event(
                config,
                event,
                event_context,
                manager,
                manager_middlewares_executor,
                silent=silent,
            ):
                yield i

        if not event.propagation_stopped:
            if manager is not None:
                event.__inherit_manager__(manager)
            for subrouter in self._sub_routers.values():
                async for e in subrouter.propagate_event(config, event, event_context, silent):
                    yield e

        if manager is not None:
            event.__renounce_manager__(manager)

        if manager_middlewares_executor:
            try:
                await manager_middlewares_executor.finalize_middlewares()
            except FinalizingError as e:
                yield e.__cause__

    async def _inner_propagate_event(
        self,
        config: DispatcherConfig,
        event: Event,
        event_context: dict[str, Any],
        manager: HandlerManager,
        manager_middlewares_executor: MiddlewaresExecutor,
        silent: bool = False,
    ):

        wrapped_filter = MiddlewareWrappedCallable(
            manager.filter.execute,
            middlewares=manager.collect_middlewares(MiddlewareManagerTypes.MANAGER_OUTER, event),
        )
        event_context = {
            **event_context,
            config.default_names_remap.get('router', 'router'): self,
        }

        try:
            filter_result = await wrapped_filter(
                callable_args=(
                    manager._config.filter_positional_only_args,
                    event_context,
                ),
                middlewares_args=manager._config.middleware_positional_only_args,
                data=event_context,
                finalize=False,
                executor=manager_middlewares_executor,
            )
        except _EarlyFinalized:
            filter_result = False
        except FinalizingError as e:
            yield e.__cause__
            return

        if not filter_result:
            try:
                await manager_middlewares_executor.finalize_middlewares()
            except FinalizingError as e:
                yield e.__cause__
            return

        wrapped_execute_manager_handlers = MiddlewareWrappedCallable(
            manager.execute_handlers,
            middlewares=manager.collect_middlewares(MiddlewareManagerTypes.MANAGER_INNER, event),
        )

        try:
            gen = await wrapped_execute_manager_handlers(
                callable_args=(config, event, event_context, silent),
                middlewares_args=manager._config.middleware_positional_only_args,
                data=event_context,
                executor=manager_middlewares_executor,
                finalize=False,
            )
        except _EarlyFinalized:
            return
        except FinalizingError as e:
            yield e.__cause__
            return

        async for task_or_exception in gen:
            yield task_or_exception

    @property
    def name(self) -> str:
        return self._name

    @property
    def root_router(self) -> Self:
        if self.parent_router is None:
            return self
        return self.parent_router.root_router

    @property
    def chain_to_root_router(self) -> Generator[Self, None, None]:
        curr_router: Self | None = self
        while curr_router is not None:
            yield curr_router
            curr_router = curr_router.parent_router

    @property
    def chain_to_tails(self) -> Generator[Self, bool | None, None]:
        """
        Generator that traverses the router chain from the current router to all sub-routers (tail nodes).

        The traversal is performed in depth-first order: first the current router, then recursively
        all its sub-routers. The generator supports a branch-skipping mechanism: if you send ``True``
        to the generator, the sub-routers of the current node will be skipped.

        :yields: Routers in depth-first traversal order.
        :rtype: Generator[Self, None, None]

        .. note::
           This property uses generator.send() protocol to allow skipping branches during traversal.
           Sending ``True`` will skip the sub-routers of the last yielded router.

        **Examples:**

        Basic iteration over all routers::

        .. code-block:: python
            for router in main_router.chain_to_tails:
                print(router.name)

        Skipping sub-routers conditionally:

        .. code-block:: python
            def should_skip(router: Router) -> bool:
                return router.name == 'router_to_skip'

            def process_router(router: Router) -> None:
                gen = main_router.chain_to_tails

                try:
                    current_router = next(gen)
                except StopIteration:
                    return

                while True:
                    try:
                        if should_skip(current_router):
                            current_router = gen.send(True) # Skip sub-routers of this node
                            continue

                        # Do something with current_router
                        ...
                    except StopIteration:
                        return
        """
        skip_current = yield self

        if skip_current:
            return

        for sub_router in self._sub_routers.values():
            sub_router_gen = sub_router.chain_to_tails

            try:
                current = next(sub_router_gen)
            except StopIteration:
                continue

            while True:
                skip = yield current

                try:
                    current = sub_router_gen.send(skip)
                except StopIteration:
                    break

    @property
    def parent_router(self) -> Self | None:
        return self._parent

    @parent_router.setter
    def parent_router(self, router: Self) -> None:
        # if type(router) is not type(self):
        #     raise TypeError(
        #         f'Parent router must be of the same class as this router '
        #         f'(expected {self.__class__.__name__}, got {router.__class__.__name__}).',
        #     )
        if self.parent_router:
            raise RuntimeError(
                f"Router '{self.name}' is already connected to router '{self.parent_router.name}'.",
            )

        if not isinstance(router, Router):
            raise ValueError(
                f'Router should be an instance of Router, not {type(router).__name__!r}',
            )

        if router is self:
            raise RuntimeError(
                'Cannot connect router to itself.',
            )

        for i in router.chain_to_root_router:
            if i.parent_router is self:
                raise RuntimeError('Circular connection of routers is not allowed.')  # todo: tree

        # todo: add name check

        self._parent = router
        router._sub_routers[self.name] = self

        router_logger.info('Router %s connected to router %s.', self.name, router.name)
