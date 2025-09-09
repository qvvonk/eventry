from __future__ import annotations


__all__ = ['DefaultHandlerManager']


from typing import TYPE_CHECKING, Any, Type, Generic, TypeVar
from collections.abc import Callable

from .base import HandlerManager, MiddlewareManagerTypes
from ..filter import Filter
from ..middleware_manager import MiddlewareManager


if TYPE_CHECKING:
    from eventry.asyncio.event import Event

    from ..router import Router


HandlerType = TypeVar('HandlerType', bound=Callable[..., Any])
FilterType = TypeVar('FilterType', bound=Filter)


class DefaultHandlerManager(
    HandlerManager[FilterType, HandlerType], Generic[FilterType, HandlerType]
):
    def __init__(
        self,
        router: Router,
        handler_manager_id: str,
        event_type_filter: Type[Event] | None = None,
    ):
        super().__init__(
            router=router,
            handler_manager_id=handler_manager_id,
            event_type_filter=event_type_filter,
        )

        self._add_middleware_manager(MiddlewareManagerTypes.OUTER, MiddlewareManager())
        self._add_middleware_manager(MiddlewareManagerTypes.INNER, MiddlewareManager())
        self._add_middleware_manager(MiddlewareManagerTypes.PER_HANDLER, MiddlewareManager())

    @property
    def outer_middleware(self) -> MiddlewareManager[Callable[..., Any]]:
        return self._middleware_managers[MiddlewareManagerTypes.OUTER]

    @property
    def inner_middleware(self) -> MiddlewareManager[Callable[..., Any]]:
        return self._middleware_managers[MiddlewareManagerTypes.INNER]

    @property
    def per_handler_middleware(self) -> MiddlewareManager[Callable[..., Any]]:
        return self._middleware_managers[MiddlewareManagerTypes.PER_HANDLER]
