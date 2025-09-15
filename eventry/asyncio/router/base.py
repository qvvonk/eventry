from __future__ import annotations


__all__ = ['Router']


from typing import TYPE_CHECKING, Any, Type, TypeVar
from collections.abc import Generator, AsyncGenerator

from typing_extensions import Self

from eventry.loggers import router_logger
from eventry.asyncio._exceptions import HandlerFound
from eventry.asyncio.handler_manager import HandlerManager
from eventry.asyncio.callable_wrappers import Handler


if TYPE_CHECKING:
    from eventry.asyncio.event import Event


HandlerManagerType = TypeVar('HandlerManagerType', bound=HandlerManager[Any, Any, Any, Any])


class Router:
    def __init__(self, router_id: str):
        self._router_id = router_id
        self._parent: Self | None = None
        self._children: dict[str, Self] = {}
        self._managers: dict[type[Event], HandlerManager[Any, Any, Any, Self]] = {}
        self._default_handler_manager: HandlerManager[Any, Any, Any, Self] | None = None

    def get_handler_by_id(self, handler_id: str, /) -> Handler[Any, Any] | None:
        for manager in self._managers.values():
            if handler_id in manager.handlers:
                return manager.handlers[handler_id]

        for router in self._children.values():
            result = router.get_handler_by_id(handler_id)
            if result is not None:
                return result
        return None

    async def _get_matching_handlers(
        self,
        event: Event,
        single_handler: bool,
        workflow_data: dict[str, Any],
    ) -> AsyncGenerator[tuple[Handler[Any, Any], Exception | None], None]:
        manager = self._get_handler_manager(event)

        try:
            async for handler, e in manager.get_matching_handlers(
                event,
                single_handler,
                workflow_data,
            ):
                yield handler, e

            for router in self._children.values():
                async for handler, e in router._get_matching_handlers(
                    event,
                    single_handler,
                    workflow_data,
                ):
                    yield handler, e
        except HandlerFound:
            return

    def _add_handler_manager(self, handler_manager: HandlerManagerType, /) -> HandlerManagerType:
        if not handler_manager.event_type_filter:
            raise ValueError(
                'Cannot add handler manager without event type filter. '
                'Assign it as default handler manager.',
            )  # todo: improve

        if handler_manager.event_type_filter in self._managers:
            raise RuntimeError('Router already has a manager with this event type.')  # todo

        self._managers[handler_manager.event_type_filter] = handler_manager
        return handler_manager

    def _get_handler_manager(
        self,
        event: Event | Type[Event],
        /,
    ) -> HandlerManager[Any, Any, Any, Self]:
        event_type = event if isinstance(event, type) else event.__class__
        if event_type in self._managers:
            return self._managers[event_type]

        for i in self._managers:
            if issubclass(event_type, i):
                return self._managers[i]

        if self._default_handler_manager:
            return self._default_handler_manager

        raise RuntimeError('No handler manager with this event type.')  # todo

    def _get_handler_managers_to_tail(
        self, event: Event
    ) -> Generator[HandlerManager[Any, Any, Any, Self], None]:
        for router in self.chain_to_last_router:
            yield router._get_handler_manager(event)

    @property
    def id(self) -> str:
        return self._router_id

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
    def chain_to_last_router(self) -> Generator[Self, None, None]:
        yield self
        for r in self._children.values():
            yield from r.chain_to_last_router

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
                f"Router '{self.id}' is already connected to router '{self.parent_router.id}'.",
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
        router._children[self.id] = self

        router_logger.info(
            f"Router '{self.id}' connected to router '{router.id}'.",
        )
