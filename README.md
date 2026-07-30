# Eventry

Eventry is a dependency-free Python library for asynchronous, in-process event routing and processing.

Eventry lets you create customizable routers for your own framework or application, 
or use the built-in default router for simpler use cases. 
It supports middleware and filters at every routing level: routers, handler managers, and individual handlers.


## Installation
```
pip install eventry
```


## Using built-in components
For simple use cases you can use built-in `Dispatcher`, `DefaultRouter` and `DefaultHandlerManager`.

```python
from eventry.asyncio import Dispatcher, DefaultRouter, ExtendedEvent


router = DefaultRouter(name='my_router')
dp = Dispatcher(router)


# Let's create some custom event.
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
    await dp.propagate_event(my_event)  # both handlers will be executed.

    event = ExtendedEvent()
    await dp.propagate_event(event)  # only `my_handler` will be executed.


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
```


## Creating custom routers
Eventry lets you create your custom routers.
Note: unlike `DefaultRouter`, the base `Router` has no `HandlerManager`'s or `MiddlewareStorage`'s.

```python
import asyncio

from eventry.asyncio import Router, DefaultHandlerManager, MiddlewareStorage, ExtendedEvent


class ApplicationRouter(Router):
    def __init__(self, name: str = ''):
        super().__init__(name=name)

        self.on_new_message = self.add_handler_manager(
            DefaultHandlerManager(name='on_message', event_filter='new_message')
        )

        self.on_new_order = self.add_handler_manager(
            DefaultHandlerManager(name='on_order', event_filter='new_order')
        )

    @property
    def outer_middleware(self) -> MiddlewareStorage:
        return self.middleware.get_middlewares_storage('router.outer', raise_=True)

    @property
    def inner_middleware(self) -> MiddlewareStorage:
        return self.middleware.get_middlewares_storage('router.inner', raise_=True)


# Now lets create our custom events.
class NewMessageEvent(ExtendedEvent, event_name='new_message'):
    def __init__(self, message: str):
        super().__init__()
        self.message = message


class NewOrderEvent(ExtendedEvent, event_name='new_order'):
    def __init__(self, order_id: int):
        super().__init__()
        self.order_id = order_id


# Now we can use new router and events in our application.
from eventry.asyncio import Dispatcher


router = ApplicationRouter(name='my_router')
dp = Dispatcher(router)


@router.on_new_message()
async def print_message(event: NewMessageEvent) -> None:
    print(event.message)


@router.on_new_order()
async def print_order_id(event: NewOrderEvent) -> None:
    print(event.order_id)


async def main():
    await dp.propagate_event(NewMessageEvent('Hello World!'))
    await dp.propagate_event(NewOrderEvent(12345))


if __name__ == '__main__':
    asyncio.run(main())
```