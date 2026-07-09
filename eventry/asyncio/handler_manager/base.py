from __future__ import annotations


__all__ = [
    'HandlerManager',
]

import inspect
from types import MappingProxyType
from collections.abc import Callable, Generator, Sequence, Awaitable

from typing import TYPE_CHECKING, Any, TypeVar, Literal

from eventry.asyncio.filter import Filter, FilterFromFunction, convert_filters, dummy_filter
from eventry.asyncio.callable_wrappers import Handler, CallableWrapper, MiddlewareCallable
from eventry.config import HandlerManagerConfig, _collect_args
from eventry.asyncio.middleware_manager import MiddlewareManager, MiddlewareManagerType, MiddlewareRegistrar


if TYPE_CHECKING:
    from eventry.event import Event

    EventFilterCallable = Callable[[Event], bool]
    EventFilter = EventFilterCallable | str


T = TypeVar('T')


MgrMdwsType = Literal[
    MiddlewareManagerType.MANAGER_OUTER,
    MiddlewareManagerType.MANAGER_INNER,
    MiddlewareManagerType.HANDLER_OUTER,
    MiddlewareManagerType.HANDLER_INNER,
    'manager.outer',
    'manager.inner',
    'handler.outer',
    'handler.inner'
]

ManagerMdwTypes = [
    MiddlewareManagerType.MANAGER_OUTER,
    MiddlewareManagerType.MANAGER_INNER,
    MiddlewareManagerType.HANDLER_OUTER,
    MiddlewareManagerType.HANDLER_INNER,
]


class HandlerManager:
    def __init__(self,
        name: str,
        event_filter: EventFilter | None = None,
        config: HandlerManagerConfig | None = None,
    ) -> None:
        """
        :param name: handler manager name.
        :param event_filter: event name filter.
        :param config: `HandlerManagerConfig` instance.
        """
        self._handlers: dict[str, Handler[Any]] = {}
        self._event_filter = event_filter
        self._name = name
        self._config = config or HandlerManagerConfig()
        self._middleware_managers: dict[MiddlewareManagerType, MiddlewareManager] = {}
        self._filter: Filter = dummy_filter()

        self.middleware: MiddlewareRegistrar[MgrMdwsType] = MiddlewareRegistrar(
            self, ManagerMdwTypes
        )

    def set_filter(self, filter: Any) -> None:  # todo: ManagerFilterType
        self._filter = filter if isinstance(filter, Filter) else FilterFromFunction(filter)

    def remove_filter(self) -> None:
        self._filter = dummy_filter()

    def get_middleware_manager(
        self,
        manager_type: MgrMdwsType
    ) -> MiddlewareManager | None:
        try:
            mdw_type = MiddlewareManagerType(manager_type)
        except ValueError:
            return None
        return self._middleware_managers.get(mdw_type)

    def set_middleware_manager(
        self,
        manager_type: MgrMdwsType,
        manager: MiddlewareManager | None
    ) -> None:
        if manager is not None and not isinstance(manager, MiddlewareManager):
            raise TypeError(
                f'Middleware manager must be an instance of MiddlewareManager, '
                f'not {type(manager)!r}.'
            )

        try:
            manager_type = MiddlewareManagerType(manager_type)
        except ValueError:
            raise ValueError(f'Invalid middleware manager type: {manager_type!r}.') from None

        if manager_type not in ManagerMdwTypes:
            raise ValueError(
                f'Handler manager does not support {manager_type!r} middleware manager.'
            )

        if manager is not None:
            self._middleware_managers[manager_type] = manager
        else:
            self._middleware_managers.pop(manager_type, None)

    def check_event(self, event: Event) -> bool:
        if self.event_filter is None:
            return True
        if isinstance(self.event_filter, str):
            return self.event_filter == event.name

        return self.event_filter(event)

    def _create_handler_obj(
        self,
        handler: Any,  # todo
        event_filter: EventFilter | None = None,
        handler_id: str | None = None,
        filter: Any = None,
        as_task: bool = False,
        inner_middlewares: Sequence[Any] | None = None,
        outer_middlewares: Sequence[Any] | None = None,
    ) -> Handler[Any]:
        if not handler_id:
            handler_id = gen_default_handler_id(handler)
            while handler_id in self._handlers:
                handler_id += '_'

        handler_obj = Handler(
            handler,
            handler_id=handler_id,
            event_filter=event_filter,
            filter=convert_filters([filter])[0] if filter is not None else None,
            as_task=as_task,
            inner_middlewares=inner_middlewares,
            outer_middlewares=outer_middlewares,
        )
        return handler_obj

    def _register_handler(self, handler: Handler[Any]) -> None:
        """
        Registers handler to this handler manager.

        Before registration, traverses the entire router network (starting from the root router)
        to check for duplicate handler IDs. If a handler with the same ID is found anywhere
        in the network, raises a ``ValueError``.

        :param handler: ``Handler`` instance to register.

        :raises ValueError: if a handler with the same ID already exists in the router network.
        """
        if handler.id in self._handlers:
            raise ValueError(f'Handler with ID {handler.id} already exists in this manager.')
        self._handlers[handler.id] = handler

    def get_matching_handlers(self, event: Event) -> Generator[Handler[Any], None]:
        """
        Iterates through all registered handlers and yields those whose filters
        match the given event.

        :param event: The incoming event to check against handler filters.

        :return: An async generator yielding handlers that should handle the event.
        """
        for handler in self._handlers.values():

            if self.event_filter is not None:
                yield handler
            else:
                if handler.check_event(event):
                    yield handler

    def __call__(
        self,
        filter: Any = None, # todo
        /,
        *,
        event_filter: EventFilter | None = None,
        handler_id: str | None = None,
        as_task: bool = False,
        inner_middlewares: Sequence[Any] | None = None,
        outer_middlewares: Sequence[Any] | None = None,
    ) -> Callable[[T], T]:
        def inner(handler: T) -> T:
            handler_obj = self._create_handler_obj(
                handler=handler,
                event_filter=event_filter,
                handler_id=handler_id,
                filter=filter,
                as_task=as_task,
                inner_middlewares=inner_middlewares,
                outer_middlewares=outer_middlewares,
            )

            self._register_handler(handler_obj)
            return handler

        return inner

    @property
    def handlers(self) -> MappingProxyType[str, Handler[Any]]:
        """
        A read-only mapping of handler IDs to their corresponding ``Handler`` instances,
        registered in this manager.
        """
        return MappingProxyType(self._handlers)

    @property
    def name(self) -> str:
        return self._name

    @property
    def event_filter(self) -> EventFilter | None:
        return self._event_filter

    @property
    def config(self) -> HandlerManagerConfig:
        return self._config

    @property
    def filter(self) -> Filter:
        return self._filter

    # ---- Big todo ----
    def _middlewares(
        self, scope: MgrMdwsType, extend_with: Sequence[MiddlewareCallable[Any]] | None = None
    ) -> list[MiddlewareCallable[Any]]:
        result = list(self.get_middleware_manager(scope) or [])
        if extend_with:
            result.extend(extend_with)
        return result

    def _middleware_wrapper_factory_factory(
        self,
        collect_args_callable
    ) -> Callable[
        [Callable[[dict[str, Any], Any]], Callable[[dict[str, Any], Any]] | None],
        Callable[[dict[str, Any]], Any]
    ]:
        def middleware_wrapper_factory(wrapping_callable, wrapped_callable):
            async def wrapped(di):
                nonlocal wrapping_callable
                if not isinstance(wrapping_callable, CallableWrapper):
                    wrapping_callable = CallableWrapper(wrapping_callable)

                data = di | {'di': di}
                if wrapped_callable is not None:
                    data.update({'next_call': wrapped_callable})
                return await wrapping_callable(collect_args_callable(di), data)
            return wrapped
        return middleware_wrapper_factory

    def _execute_handler_factory(self, handler: Handler[Any]) -> Callable[..., Awaitable[Any]]:
        async def execute_handler(**di):
            return await handler(self.config.collect_handler_args(di), di)
        return execute_handler

    async def _execute_handler(self, handler: Handler[Any], **di) -> Any:
        wrapped = MiddlewareManager.wrap_with_middlewares(
            self._execute_handler_factory(handler),
            self._middlewares('handler.inner', handler.inner_middlewares),
            self._middleware_wrapper_factory_factory(self.config.collect_handler_inner_mdw_args)
        )
        return await wrapped(di)

    def _execute_handler_with_a_filter_factory(self, handler: Handler[Any]):
        async def execute_handler_with_a_filter(**di):
            r = await handler.filter.execute(self.config.collect_handler_filter_args(di), di)
            if not r and not isinstance(r, dict):
                return r

            if isinstance(r, dict):
                di = di | r
            return await self._execute_handler(handler, **di)
        return execute_handler_with_a_filter

    async def _execute_handler_with_a_filter(self, handler: Handler[Any], **di):
        wrapped = MiddlewareManager.wrap_with_middlewares(
            self._execute_handler_with_a_filter_factory(handler),
            self._middlewares('handler.outer', handler.outer_middlewares),
            self._middleware_wrapper_factory_factory(self.config.collect_handler_outer_mdw_args)
        )
        return await wrapped(di)

    def _execute_handlers_factory(self, event: Event):
        async def execute_handlers(**di):
            for i in self.get_matching_handlers(event):
                await self._execute_handler_with_a_filter(i, **di)
                if event.propagation_stopped:
                    return

        return execute_handlers

    async def _execute_handlers(self, event: Event, **di):
        wrapped = MiddlewareManager.wrap_with_middlewares(
            self._execute_handlers_factory(event),
            self._middlewares('manager.inner'),
            self._middleware_wrapper_factory_factory(self.config.collect_manager_inner_mdw_args)
        )
        return await wrapped(di)

    def _execute_handlers_with_mgr_filter_factory(self, event: Event):
        async def execute_handlers_with_mgr_filter(**di):
            r = await self.filter.execute(self.config.collect_manager_filter_args(di), di)
            if r is False or r is None:
                return r
            return await self._execute_handlers(event, **di)
        return execute_handlers_with_mgr_filter

    async def propagate_event(self, event: Event, **di):
        wrapped = MiddlewareManager.wrap_with_middlewares(
            self._execute_handlers_with_mgr_filter_factory(event),
            self._middlewares('manager.outer'),
            self._middleware_wrapper_factory_factory(self.config.collect_manager_outer_mdw_args)
        )

        self.config.update_di_with_manager_outer_mdw_args(di)
        self.config.update_di_with_manager_filter_args(di)
        self.config.update_di_with_manager_inner_mdw_args(di)
        self.config.update_di_with_handler_outer_mdw_args(di)
        self.config.update_di_with_handler_filter_args(di)
        self.config.update_di_with_handler_inner_mdw_args(di)
        self.config.update_di_with_handler_args(di)

        return await wrapped(di)
    # ---- ---- ----


def gen_default_handler_id(handler: Any):
    if inspect.isfunction(handler) or inspect.ismethod(handler) or inspect.isclass(handler):
        return f'{handler.__qualname__}'
    return f'{handler.__class__.__qualname__}'
