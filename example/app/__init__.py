from example.custom_event import MyEvent
from example.custom_router import MyRouter
from typing import Any
from typing_extensions import reveal_type, TypeVar
from example.custom_handler_manager import HandlerProtocol

r = MyRouter(router_id='router')


@r.on_my_event
def my_handler(e: MyEvent) -> Any:
    print(e.object)



async def main():
    event = MyEvent(