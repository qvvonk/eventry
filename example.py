from eventry.asyncio.router import DefaultRouter
from eventry.asyncio.dispatcher import DefaultDispatcher
from eventry.asyncio.event import ExtendedEvent
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
            },
            'eventry.router': {
                'level': logging.DEBUG,
                'handlers': ['console'],
            }
        }
    }
)


dp = DefaultDispatcher()


@dp.on_event(on_event=ExtendedEvent)
def handler(event: ExtendedEvent) -> None:
    print(event)


async def main() -> None:
    event = ExtendedEvent()
    await dp.propagate_event(event)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())