from __future__ import annotations

from eventry.asyncio.handler_manager import DefaultHandlerManager

from .base import Router


class DefaultRouter(Router):
    def __init__(self, name: str):
        super().__init__(name=name)

        self.set_default_handler_manager(
            DefaultHandlerManager(
                self,
                handler_manager_id='default',
                event_type_filter=None,
            ),
        )

    @property
    def on_event(self) -> DefaultHandlerManager:
        return self._default_handler_manager
