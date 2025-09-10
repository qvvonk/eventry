from example.custom_event import MyEvent
from example.custom_router import MyRouter
from typing import Any
from typing_extensions import reveal_type, TypeVar
from example.custom_handler_manager import HandlerProtocol

r = MyRouter(router_id='router')


@r.on_my_event
async def my_handler_z() -> None:
    print('nother')
