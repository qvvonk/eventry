from eventry.asyncio.router import DefaultRouter
from eventry.asyncio.dispatcher import DefaultDispatcher
from eventry.asyncio.event import ExtendedEvent


router = DefaultRouter(name='test')
dp = DefaultDispatcher()
dp.connect_router(router)

@router.on_event()
async def print_event(event):
    print(event)


async def main():
    e = ExtendedEvent()
    await dp.event_entry(event=e)


if __name__ == '__main__':
    import logging
    import asyncio

    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(main())
