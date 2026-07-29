# Eventry

Eventry is a dependency-free Python library for asynchronous, in-process event routing and processing.

Eventry lets you create customizable routers for your own framework or application, 
or use the built-in default router for simpler use cases. 
It supports middleware and filters at every routing level: routers, handler managers, and individual handlers.


## Using built-in components.
For simple use cases you can use built-in `Dispatcher`, `DefaultRouter` and `DefaultHandlerManager`.

```python
from eventry.asyncio import Dispatcher, DefaultRouter, ExtendedEvent


router = DefaultRouter(name='my_router')
dp = Dispatcher(router)


class MyEvent(ExtendedEvent, event_name='my_event'):
    def __init__(self, trigger: str):
        super().__init__()
        self.trigger = trigger


# Default router has only one handler manager that does not filter events and accepts all of them.
# Type annotations don't filter events.
@router.on_event()
async def my_handler(event: ExtendedEvent) -> None:
    print(event.__event_name__)


# If you want to filter events by type without creating custom routers, you can use handler filters.
@router.on_event(lambda event: event.name == 'my_event')
async def my_handler_with_filter(event: MyEvent):
    print(event.trigger)


async def main():
    my_event = MyEvent('qvvonk')
    await dp.propagate_event(my_event)  # only `my_handler` will be executed.
    
    event = ExtendedEvent()
    await dp.propagate_event(event)  # both handlers will be executed.


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
```