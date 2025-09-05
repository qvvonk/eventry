from __future__ import annotations


__all__ = [
    'Router',
]

from typing import TYPE_CHECKING, Any, Generator, AsyncGenerator, Type, TypeVar

from eventry.loggers import router_logger
from eventry.asyncio.event import Event
from eventry.asyncio.handler_manager import HandlerManager


if TYPE_CHECKING:
    from eventry.asyncio.bases import HandlerInfo

E = TypeVar('E', bound=Event[Any])


class Router:
    def __init__(
        self,
        name: str | None = None,
        default_handler_manager: HandlerManager[Event[Any]] | None = ...,
    ) -> None:
        self._name = name or f'Router{id(self)}'
        self._parent_router: Router | None = None
        self._inner_routers: dict[str, Router] = {}

        if default_handler_manager is Ellipsis:
            self._default_handler_manager = HandlerManager(self, 'default', None)
        elif default_handler_manager is None:
            self._default_handler_manager = None
        else:
            self._default_handler_manager = default_handler_manager

        self._managers = {}

    def connect_router(self, router: Router) -> None:
        router.parent_router = self

    def connect_routers(self, *routers: Router) -> None:
        for i in routers:
            self.connect_router(i)

    def add_manager(self, event_type: Type[E], name: str) -> HandlerManager[E]:
        manager = HandlerManager(self, event_type_filter=event_type, name=name)
        self._managers[event_type] = manager
        return manager

    def get_handler_by_id(self, handler_id: str, /) -> HandlerInfo | None:
        for manager in self._managers.values():
            try:
                return manager.handlers[handler_id]
            except KeyError:
                continue

        for router in self._inner_routers.values():
            result = router.get_handler_by_id(handler_id)
            if result is not None:
                return result
        return None

    async def get_matching_handlers(
        self,
        event: Event[Any],
        workflow_data: dict[str, Any],
    ) -> AsyncGenerator[tuple[HandlerInfo, Exception | None], None]:
        manager = self.get_manager_by_event(event)

        async for handler, e in manager.get_matching_handlers(event, workflow_data):
            yield handler, e

        for router in self._inner_routers.values():
            async for handler, e in router.get_matching_handlers(event, workflow_data):
                yield handler, e

    def get_manager_by_event(self, event: Event[Any]) -> HandlerManager[Any]:
        for t, m in self._managers.items():
            if isinstance(event, t):
                return m
        if self._default_handler_manager is None:
            raise RuntimeError(f'Unable to find handler manager for {event.__class__.__name__}.')
        return self._default_handler_manager

    @property
    def root_router(self) -> Router:
        if self.parent_router is None:
            return self
        return self.parent_router.root_router

    @property
    def chain_to_root_router(self) -> Generator[Router, None, None]:
        curr_router: Router | None = self
        while curr_router is not None:
            yield curr_router
            curr_router = curr_router.parent_router

    @property
    def chain_to_last_router(self) -> Generator[Router, None, None]:
        yield self
        for r in self._inner_routers.values():
            yield from r.chain_to_last_router

    @property
    def parent_router(self) -> Router | None:
        return self._parent_router

    @parent_router.setter
    def parent_router(self, router: Router) -> None:
        if self.parent_router:
            raise RuntimeError(
                f"Router '{self.name}' is already connected to router "
                f"'{self.parent_router.name}'.",
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

        self._parent_router = router
        router._inner_routers[self.name] = self
        router_logger.info(
            f"Router '{self.name}' connected to router '{router.name}'.",
        )

    @property
    def name(self) -> str:
        return self._name
