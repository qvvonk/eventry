from __future__ import annotations


__all__ = ['Router']


from collections.abc import Generator

from typing_extensions import TYPE_CHECKING, Any, Self, Type, TypeVar

from eventry.loggers import router_logger
from eventry.asyncio.handler_manager import HandlerManager
from eventry.asyncio.callable_wrappers import Handler


if TYPE_CHECKING:
    from eventry.asyncio.event import Event


HandlerManagerT = TypeVar('HandlerManagerT', bound=HandlerManager[Any, Any, Any, Any])


class Router:
    def __init__(self, name: str):
        self._name = name
        self._parent: Self | None = None
        self._children: dict[str, Self] = {}
        self._managers: dict[type[Event], HandlerManager[Any, Any, Any, Self]] = {}
        self._managers_by_id: dict[str, HandlerManager[Any, Any, Any, Self]] = {}
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

    def _add_handler_manager(self, handler_manager: HandlerManagerT, /) -> HandlerManagerT:
        if not handler_manager.event_type_filter:
            raise ValueError(
                'Cannot add handler manager without event type filter. '
                'Assign it as default handler manager.',
            )  # todo: improve

        if handler_manager.id in self._managers_by_id or (
            self._default_handler_manager
            and self._default_handler_manager.id == handler_manager.id
        ):
            raise ValueError(
                f'Manager with id {handler_manager.id!r} already added to router {self._name!r}. ',
            )

        self._managers[handler_manager.event_type_filter] = handler_manager
        self._managers_by_id[handler_manager.id] = handler_manager
        return handler_manager

    def get_handler_manager(
        self,
        event: Event | Type[Event],
        /,
    ) -> HandlerManager[Any, Any, Any, Self]:
        event_type = event if isinstance(event, type) else type(event)
        if event_type in self._managers:
            return self._managers[event_type]

        for i in self._managers:
            if issubclass(event_type, i):
                return self._managers[i]

        if self._default_handler_manager:
            return self._default_handler_manager

        raise RuntimeError('No handler manager with this event type.')  # todo

    def _get_handler_managers_to_tail(
        self,
        event: Event,
    ) -> Generator[HandlerManager[Any, Any, Any, Self], None]:
        for router in self.chain_to_last_router:
            yield router.get_handler_manager(event)

    def connect_router(self, router: Router) -> None:
        router.parent_router = self

    def connect_routers(self, *routers: Router) -> None:
        for i in routers:
            i.parent_router = self

    def __getitem__(self, item: str | Event | type[Event]) -> HandlerManager[Any, Any, Any, Self]:
        if isinstance(item, str):
            if self._default_handler_manager and self._default_handler_manager.id == item:
                return self._default_handler_manager
            return self._managers_by_id[item]
        return self.get_handler_manager(item)

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
        router._children[self.name] = self

        router_logger.info(
            f"Router '{self.name}' connected to router '{router.name}'.",
        )
