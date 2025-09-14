from __future__ import annotations

from eventry.asyncio.handler_manager import DefaultHandlerManager

from .base import Router


class DefaultRouter(Router):
    def __init__(self, router_id: str):
        super().__init__(router_id=router_id)

        self._default_handler_manager: DefaultHandlerManager = DefaultHandlerManager(
            self,
            handler_manager_id='default',
            event_type_filter=None,
        )

    @property
    def on_event(self) -> DefaultHandlerManager:
        return self._default_handler_manager
