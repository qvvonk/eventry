from __future__ import annotations
from .base import Router

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eventry.asyncio.handler_manager import HandlerManager
    from eventry.asyncio.event import Event


class DefaultRouter(Router):
    def __init__(self, name: str | None = None):
        super().__init__(name)

    @property
    def on_event(self) -> HandlerManager[Event[Any]]:
        return self._default_handler_manager