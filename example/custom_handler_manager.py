from eventry.asyncio.handler_manager import HandlerManager, MiddlewareManagerTypes
from .custom_event import MyEvent
from typing import Any, Type
from collections.abc import Callable, Awaitable
from eventry.asyncio.filter import Filter
from eventry.asyncio.router import Router
from eventry.asyncio.middleware_manager import MiddlewareManager
from .config import handler_manager_config


HandlerType = Callable[[MyEvent], Any]
NextMiddlewareType = Callable[[], Awaitable[Any]]

class MyHandlerManager(HandlerManager[Filter, HandlerType]):
    def __init__(self, router: Router, handler_manager_id: str, event_type_filter: Type[MyEvent] | None = None):
        super().__init__(
            router=router,
            handler_manager_id=handler_manager_id,
            event_type_filter=event_type_filter,
            config=handler_manager_config
        )

        self._add_middleware_manager(
            MiddlewareManagerTypes.OUTER, MiddlewareManager()
        )

        self._add_middleware_manager(
            MiddlewareManagerTypes.INNER, MiddlewareManager()
        )

        self._add_middleware_manager(
            MiddlewareManagerTypes.PER_HANDLER, MiddlewareManager()
        )

    @property
    def outer_middleware(self) -> MiddlewareManager[Callable[[NextMiddlewareType], Any]]:
        return self._middleware_managers[MiddlewareManagerTypes.OUTER]

    @property
    def inner_middleware(self) -> MiddlewareManager[Callable[[NextMiddlewareType], Any]]:
        return self._middleware_managers[MiddlewareManagerTypes.INNER]

    @property
    def per_handler_middleware(self) -> MiddlewareManager[Callable[[NextMiddlewareType], Any]]:
        return self._middleware_managers[MiddlewareManagerTypes.PER_HANDLER]
