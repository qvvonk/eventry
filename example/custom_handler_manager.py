from __future__ import annotations

from typing import TYPE_CHECKING, Any, Type, TypeVar, Protocol
from collections.abc import Callable, Awaitable

from eventry.asyncio.filter import Filter
from eventry.asyncio.handler_manager import HandlerManager, MiddlewareManagerTypes
from eventry.asyncio.middleware_manager import MiddlewareManager

from .config import handler_manager_config
from .custom_event import MyEvent


if TYPE_CHECKING:
    from .custom_router import MyRouter


NextMiddlewareType = Callable[[], Awaitable[Any]]
R = TypeVar('R', bound=Any)


class HandlerProtocol(Protocol):
    def __call__(self, __event: MyEvent, *__args: Any, **__kwargs: Any) -> Any:
        pass


class MiddlewareProtocol(Protocol):
    def __call__(self, __next_call: NextMiddlewareType, *__args: Any, **__kwargs: Any) -> Any:
        pass


class MyHandlerManager(HandlerManager[Filter, HandlerProtocol, 'MyRouter']):
    def __init__(
        self,
        router: MyRouter,
        handler_manager_id: str,
        event_type_filter: Type[MyEvent] | None = None,
    ):
        super().__init__(
            router=router,
            handler_manager_id=handler_manager_id,
            event_type_filter=event_type_filter,
            config=handler_manager_config,
        )

        self._add_middleware_manager(
            MiddlewareManagerTypes.OUTER,
            MiddlewareManager(),
        )

        self._add_middleware_manager(
            MiddlewareManagerTypes.INNER,
            MiddlewareManager(),
        )

        self._add_middleware_manager(
            MiddlewareManagerTypes.PER_HANDLER,
            MiddlewareManager(),
        )

    @property
    def outer_middleware(self) -> MiddlewareManager[MiddlewareProtocol]:
        return self._middleware_managers[MiddlewareManagerTypes.OUTER]

    @property
    def inner_middleware(self) -> MiddlewareManager[MiddlewareProtocol]:
        return self._middleware_managers[MiddlewareManagerTypes.INNER]

    @property
    def per_handler_middleware(self) -> MiddlewareManager[MiddlewareProtocol]:
        return self._middleware_managers[MiddlewareManagerTypes.PER_HANDLER]
