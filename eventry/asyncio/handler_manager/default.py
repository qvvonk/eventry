from __future__ import annotations


__all__ = ['DefaultHandlerManager']


from typing import TYPE_CHECKING, Any
from collections.abc import Callable
from .base import HandlerManager
from eventry.asyncio.middleware_manager import MiddlewareManager

if TYPE_CHECKING:
    from eventry.asyncio.filter import Filter
    from .base import EventFilter
    from eventry.config import HandlerManagerConfig


FilterCallable = Callable[..., bool | None | dict[str, Any]]
FilterT = FilterCallable | Filter
MiddlewareT = Callable[..., Any]
HandlerT = Callable[..., Any]

ManagerOuterMdwT = MiddlewareT
ManagerInnerMdwT = MiddlewareT
HandlerOuterMdwT = MiddlewareT
HandlerInnerMdwT = MiddlewareT
ManagerFilterT = FilterT
HandlerFilterT = FilterT


class DefaultHandlerManager(
    HandlerManager[
        ManagerOuterMdwT,
        ManagerFilterT,
        ManagerInnerMdwT,
        HandlerOuterMdwT,
        HandlerFilterT,
        HandlerInnerMdwT,
        HandlerT,
    ]
):
    def __init__(
        self,
        name: str,
        event_filter: EventFilter | None = None,
        config: HandlerManagerConfig | None = None,
    ) -> None:
        super().__init__(
            name=name,
            event_filter=event_filter,
            config=config
        )

        self.set_middleware_manager('manager.outer', MiddlewareManager())
        self.set_middleware_manager('manager.inner', MiddlewareManager())
        self.set_middleware_manager('handler.outer', MiddlewareManager())
        self.set_middleware_manager('handler.inner', MiddlewareManager())

    @property
    def manager_outer_middleware(self):
        return self.middleware('manager.inner')

    @property
    def manager_inner_middleware(self):
        return self.middleware('manager.inner')

    @property
    def handler_outer_middleware(self):
        return self.middleware('handler.outer')

    @property
    def handler_inner_middleware(self):
        return self.middleware('handler.inner')