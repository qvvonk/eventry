from eventry.asyncio.dispatcher import DefaultDispatcher
from eventry.asyncio.router import DefaultRouter
from eventry.asyncio.event import ExtendedEvent
from eventry.exceptions import AbortExecution

dp = DefaultDispatcher()
r = DefaultRouter(router_id='Router')

r.parent_router = dp



def dp_middleware():
    print("DP MIDDLEWARE PRE")
    yield
    print("DP MIDDLEWARE POST")


def dp_middleware2():
    print("DP MIDDLEWARE2 PRE")
    yield
    print("DP MIDDLEWARE2 POST")

def handler_middleware():
    print("HANDLER INNER NON-WRAPPING MIDDLEWARE")
    raise AbortExecution()


dp.on_event.outer_middleware(dp_middleware)
dp.on_event.outer_middleware(dp_middleware2)


@r.on_event(middlewares=[handler_middleware])
def handler(event: ExtendedEvent):
    print(f'Handler for event {event}')

@r.on_event
def handler2():
    print(f'HANDLER 2')


async def main():
    event = ExtendedEvent()
    await dp.propagate_event(event=event)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())