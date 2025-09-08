from .base import Router
from eventry.asyncio.handler_manager import DefaultHandlerManager
from eventry.asyncio.filter import Filter
from collections.abc import Callable
from typing import Any


class DefaultRouter(Router):
    def __init__(self, router_id: str):
        super().__init__(router_id=router_id)

        self._default_handler_manager: DefaultHandlerManager[Filter, Callable[..., Any]] = DefaultHandlerManager(
            self, handler_manager_id='default', event_type_filter=None
        )

    @property
    def on_event(self) -> DefaultHandlerManager[Filter, Callable[..., Any]]:
        return self._default_handler_manager
