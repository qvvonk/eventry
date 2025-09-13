from __future__ import annotations


__all__ = ['DefaultHandlerManager']


from typing import TYPE_CHECKING, Any, Type, TypeVar
from collections.abc import Callable

from .base import HandlerManager, MiddlewareManagerTypes
from ..middleware_manager import MiddlewareManager
from eventry.asyncio.default_types import HandlerType, FilterType

if TYPE_CHECKING:
    from eventry.asyncio.event import Event
    from ..router import Router


HandlerTypeT = TypeVar('HandlerTypeT', bound=HandlerType, default=HandlerType)
FilterTypeT = TypeVar('FilterTypeT', bound=FilterType, default=FilterType)
RouterType = TypeVar('RouterType', bound='Router', default='Router')


class DefaultHandlerManager(HandlerManager[FilterTypeT, HandlerTypeT, RouterType]):
    def __init__(
        self,
        router: RouterType,
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

    @property
    def outer_middleware(self) -> MiddlewareManager[Callable[..., Any]]:
        return self._middleware_managers[MiddlewareManagerTypes.OUTER]

    @property
    def inner_middleware(self) -> MiddlewareManager[Callable[..., Any]]:
        return self._middleware_managers[MiddlewareManagerTypes.INNER]
