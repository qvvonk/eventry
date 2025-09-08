from ..custom_router import MyRouter
from ..custom_event import MyEvent


r = MyRouter(router_id='router')


@r.on_my_event
def my_handler(e: MyEvent) -> None:
    print(e.object)
