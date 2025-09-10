from __future__ import annotations

from .base import Router
from eventry.asyncio.handler_manager import DefaultHandlerManager
from eventry.asyncio.filter import Filter
from eventry.asyncio.default_types import FilterType, HandlerType
from collections.abc import Callable
from typing import Any


class DefaultRouter(Router):
    def __init__(self, router_id: str):
        super().__init__(router_id=router_id)

        self._default_handler_manager: DefaultHandlerManager[FilterType, HandlerType, DefaultRouter] = DefaultHandlerManager(
            self, handler_manager_id='default', event_type_filter=None
        )

    @property
    def on_event(self) -> DefaultHandlerManager[FilterType, HandlerType, DefaultRouter]:
        return self._default_handler_manager
