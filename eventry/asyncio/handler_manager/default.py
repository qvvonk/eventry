from __future__ import annotations


__all__ = ['DefaultHandlerManager']


from typing import TYPE_CHECKING

from eventry.asyncio.config import Context, FromContext
from eventry.asyncio.middleware import MiddlewareStorage
from eventry.asyncio.handler_manager.base import HandlerManagerConfig, HandlerManagerDefaultType


if TYPE_CHECKING:
    from .base import EventFilter


class DefaultHandlerManager(HandlerManagerDefaultType):
    def __init__(
        self,
        name: str,
        event_filter: EventFilter | None = None,
    ) -> None:
        super().__init__(
            name=name,
            event_filter=event_filter,
            config=HandlerManagerConfig(
                manager_outer_mdw_args=(FromContext('next_call'), Context),
                manager_inner_mdw_args=(FromContext('next_call'), Context),
                handler_outer_mdw_args=(FromContext('next_call'), Context),
                handler_inner_mdw_args=(FromContext('next_call'), Context),
            ),
        )

        self.middleware['manager.outer'] = MiddlewareStorage()
        self.middleware['manager.inner'] = MiddlewareStorage()
        self.middleware['handler.outer'] = MiddlewareStorage()
        self.middleware['handler.inner'] = MiddlewareStorage()

    @property
    def manager_outer_middleware(self) -> MiddlewareStorage:
        return self.middleware['manager.outer']

    @property
    def manager_inner_middleware(self) -> MiddlewareStorage:
        return self.middleware['manager.inner']

    @property
    def handler_outer_middleware(self) -> MiddlewareStorage:
        return self.middleware['handler.outer']

    @property
    def handler_inner_middleware(self) -> MiddlewareStorage:
        return self.middleware['handler.inner']
