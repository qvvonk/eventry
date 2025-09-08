from eventry.asyncio.router import Router
from .custom_handler_manager import MyHandlerManager, HandlerType
from eventry.asyncio.filter import Filter
from .custom_event import MyEvent


class MyRouter(Router):
    def __init__(self, router_id: str):
        super().__init__(
            router_id=router_id
        )

        self._add_handler_manager(
            MyHandlerManager(self, handler_manager_id='on_my_event', event_type_filter=MyEvent)
        )

    @property
    def on_my_event(self) -> MyHandlerManager[Filter, MyHandlerManager]:
        return self._managers[MyEvent]

