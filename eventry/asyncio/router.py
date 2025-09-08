from __future__ import annotations


__all__ = ['Router']


from typing import Any, TypeVar, Type, TYPE_CHECKING
from collections.abc import Generator

from eventry.loggers import router_logger

from .handler_manager import HandlerManager
from .callable_wrappers import Handler


if TYPE_CHECKING:
    from eventry.asyncio.event import Event


E = TypeVar('E', bound=HandlerManager[Any, Any])


class Router:
    def __init__(self, router_id: str):
        self._router_id = router_id
        self._parent: Router | None = None
        self._children: dict[str, Router] = {}
        self._managers: dict[type[Event], HandlerManager[Any, Any]] = {}
        self._default_handler_manager: HandlerManager[Any, Any] | None = None

    def get_handler_by_id(self, handler_id: str, /) -> Handler[Any, Any] | None:
        for manager in self._managers.values():
            if handler_id in manager.handlers:
                return manager.handlers[handler_id]

        for router in self._children.values():
            result = router.get_handler_by_id(handler_id)
            if result is not None:
                return result
        return None

    def _add_handler_manager(self, handler_manager: E, /) -> E:
        if not handler_manager.event_type_filter:
            raise ValueError('Cannot add handler manager without event type filter. '
                             'Assign it as default handler manager.')  # todo: improve

        if handler_manager.event_type_filter in self._managers:
            raise RuntimeError('Router already has a manager with this event type.')  # todo

        self._managers[handler_manager.event_type_filter] = handler_manager
        return handler_manager

    def _get_handler_manager(self, event: Event | Type[Event], /) -> HandlerManager[Any, Any]:
        event_type = event if isinstance(event, type) else event.__class__
        if event_type in self._managers:
            return self._managers[event_type]

        for i in self._managers:
            if issubclass(event_type, i):
                return self._managers[i]

        if self._default_handler_manager:
            return self._default_handler_manager

        raise RuntimeError('No handler manager with this event type.')  # todo

    @property
    def id(self) -> str:
        return self._router_id

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
        for r in self._children.values():
            yield from r.chain_to_last_router

    @property
    def parent_router(self) -> Router | None:
        return self._parent

    @parent_router.setter
    def parent_router(self, router: Router) -> None:
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
