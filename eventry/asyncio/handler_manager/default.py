from __future__ import annotations


__all__ = ['DefaultHandlerManager']


from typing import TYPE_CHECKING

from eventry.asyncio.config import DEFAULT_HANDLER_MANAGER_CONFIG
from eventry.asyncio.middleware import MiddlewareStorage
from eventry.asyncio.handler_manager.base import HandlerManagerDefaultType


if TYPE_CHECKING:
    from .base import EventFilter


class DefaultHandlerManager(HandlerManagerDefaultType):
    def __init__(
        self,
        name: str,
        event_filter: EventFilter | None = None,
    ) -> None:
        super().__init__(
            name=name, event_filter=event_filter, config=DEFAULT_HANDLER_MANAGER_CONFIG
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
