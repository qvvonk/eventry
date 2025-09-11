from example.custom_event import MyEvent
from example.custom_router import MyRouter
from typing import Any
from typing_extensions import reveal_type, TypeVar
from example.custom_handler_manager import HandlerProtocol

r = MyRouter(router_id='router')


@r.on_my_event(filter=lambda: False)
def my_handler(e: MyEvent) -> Any:
    print(e.object)


@r.on_my_event
def my_event_handler(e: MyEvent) -> Any:
    print(f'2, {e.object}')



async def main():
    event = MyEvent('some_event')
    workflow_data = {'something': 'abcd'}

    async for h, e in r.on_my_event.get_matching_handlers(event, single_handler=False, workflow_data=workflow_data):
        print(h, e)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())