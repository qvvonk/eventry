from eventry.asyncio.router import DefaultRouter
from eventry.asyncio.dispatcher import DefaultDispatcher
from eventry.asyncio.event import ExtendedEvent


router = DefaultRouter(name='test')
router2 = DefaultRouter(name='test2')
router3 = DefaultRouter(name='test3')
dp = DefaultDispatcher()
dp.connect_router(router)
router.connect_router(router2)
dp.connect_router(router3)
router.on_event.manager_outer_middleware.register_middleware(
    middleware=lambda: print('OUTER ROUTER'),
    inheritable=True
)
router.on_event.manager_outer_middleware.register_middleware(
    middleware=lambda: print('OUTER2 ROUTER'),
    inheritable=True
)
router2.on_event.manager_outer_middleware.register_middleware(
    middleware=lambda: print('OUTER ROUTER 2'),
)


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
