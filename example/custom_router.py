from __future__ import annotations

from eventry.asyncio.router import Router

from .custom_event import MyEvent
from .custom_handler_manager import MyHandlerManager


class MyRouter(Router):
    def __init__(self, router_id: str):
        super().__init__(
            router_id=router_id,
        )

        self._add_handler_manager(
            MyHandlerManager(self, handler_manager_id='on_my_event', event_type_filter=MyEvent),
        )

    @property
    def on_my_event(self) -> MyHandlerManager:
        return self._managers[MyEvent]  # type: ignore
