from __future__ import annotations


__all__ = ['DefaultHandlerManager']


from typing_extensions import TYPE_CHECKING, Type, TypeVar

from eventry.asyncio.default_types import FilterType, HandlerType, MiddlewareType

from .base import HandlerManager
from ..middleware_manager import MiddlewareManager, MiddlewareManagerTypes


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

        self._add_middleware_manager(MiddlewareManagerTypes.MANAGER_OUTER, MiddlewareManager())
        self._add_middleware_manager(MiddlewareManagerTypes.MANAGER_INNER, MiddlewareManager())
        self._add_middleware_manager(MiddlewareManagerTypes.HANDLING_PROCESS, MiddlewareManager())
        self._add_middleware_manager(MiddlewareManagerTypes.OUTER_PER_HANDLER, MiddlewareManager())
        self._add_middleware_manager(MiddlewareManagerTypes.INNER_PER_HANDLER, MiddlewareManager())

    @property
    def manager_outer_middleware(self) -> MiddlewareManager[MiddlewareT]:
        return self._middleware_managers[MiddlewareManagerTypes.MANAGER_OUTER]

    @property
    def manager_inner_middleware(self) -> MiddlewareManager[MiddlewareT]:
        return self._middleware_managers[MiddlewareManagerTypes.MANAGER_INNER]

    @property
    def handling_process_middleware(self) -> MiddlewareManager[MiddlewareT]:
        return self._middleware_managers[MiddlewareManagerTypes.HANDLING_PROCESS]

    @property
    def inner_middleware(self) -> MiddlewareManager[MiddlewareT]:
        return self._middleware_managers[MiddlewareManagerTypes.INNER_PER_HANDLER]

    @property
    def outer_middleware(self) -> MiddlewareManager[MiddlewareT]:
        return self._middleware_managers[MiddlewareManagerTypes.OUTER_PER_HANDLER]
