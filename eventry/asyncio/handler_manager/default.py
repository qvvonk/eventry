from __future__ import annotations


__all__ = ['DefaultHandlerManager']


from typing import TYPE_CHECKING, Type, TypeVar

from eventry.asyncio.default_types import FilterType, HandlerType, MiddlewareType

from .base import HandlerManager, MiddlewareManagerTypes
from ..middleware_manager import MiddlewareManager


if TYPE_CHECKING:
    from eventry.asyncio.event import Event

    from ..router import Router


HandlerT = TypeVar('HandlerT', bound=HandlerType, default=HandlerType)
FilterT = TypeVar('FilterT', bound=FilterType, default=FilterType)
MiddlewareT = TypeVar('MiddlewareT', bound=MiddlewareType, default=MiddlewareType)
RouterT = TypeVar('RouterT', bound='Router', default='Router')


class DefaultHandlerManager(HandlerManager[FilterT, HandlerT, MiddlewareT, RouterT]):
    def __init__(
        self,
        router: RouterT,
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
    def outer_middleware(self) -> MiddlewareManager[MiddlewareT]:
        return self._middleware_managers[MiddlewareManagerTypes.OUTER]

    @property
    def inner_middleware(self) -> MiddlewareManager[MiddlewareT]:
        return self._middleware_managers[MiddlewareManagerTypes.INNER]
