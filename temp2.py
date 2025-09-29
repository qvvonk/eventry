from eventry.asyncio.middleware_manager import MiddlewareWrappedCallable, MiddlewaresExecutor
from eventry.asyncio.callable_wrappers import CallableWrapper
from eventry.asyncio.dispatcher import DefaultDispatcher
from eventry.asyncio.event import Event
import logging
import sys
from logging.config import dictConfig


dictConfig(
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'console': {
                'formatter': 'brief',
                'level': logging.DEBUG,
                'class': 'logging.StreamHandler',
                'stream': sys.stdout
            }
        },
        'formatters': {
            'brief': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            }
        },
        'loggers': {
            'eventry.dispatcher': {
                'level': logging.DEBUG,
                'handlers': ['console'],
            }
        }
    }
)


dp = DefaultDispatcher()


@dp.on_event(
    on_event=Event
)
async def original_callable():
    print('|------------------------------|')
    print('|       ORIGINAL CALLABLE      |')
    print('|RAISING FROM ORIGINAL CALLABLE|')
    print('|------------------------------|')
    raise ValueError('00000000000000000')


@dp.on_event.inner_middleware
async def first_middleware():
    print('FIRST MIDDLE PRE')
    try:
        yield
    except:
        import traceback
        print(traceback.format_exc())
        print(f'FIRST MIDDLE ERROR HANDLE')
    print('FIRST MIDDLE POST')


@dp.on_event.inner_middleware
async def second_middleware():
    print('SECOND MIDDLE PRE')
    yield
    print('SECOND MIDDLE POST')


@dp.on_event.inner_middleware
async def third_middleware():
    print('THIRD MIDDLE')



async def main():
    event = Event()
    await dp.propagate_event(event)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())