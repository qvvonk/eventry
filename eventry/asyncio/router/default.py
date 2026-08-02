from __future__ import annotations


__all__ = ['DefaultRouter']

from typing import Any

from eventry.asyncio.config import DEFAULT_ROUTER_CONFIG
from eventry.asyncio.middleware import MiddlewareStorage
from eventry.asyncio.handler_manager import DefaultHandlerManager

from .base import Router


class DefaultRouter(Router[Any]):
    def __init__(self, name: str = ''):
        super().__init__(name=name, config=DEFAULT_ROUTER_CONFIG)

        self._manager = DefaultHandlerManager('DefaultHandlerManager', lambda *args: True)
        self._handler_managers['DefaultHandlerManager'] = self._manager
        self.middleware['router.outer'] = MiddlewareStorage()
        self.middleware['router.inner'] = MiddlewareStorage()

    @property
    def on_event(self) -> DefaultHandlerManager:
        return self._manager

    @property
    def outer_middleware(self) -> MiddlewareStorage:
        return self.middleware['router.outer']

    @property
    def inner_middleware(self) -> MiddlewareStorage:
        return self.middleware['router.inner']
