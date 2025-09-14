from __future__ import annotations

from typing import Any

from typing_extensions import TypeVar, reveal_type

from example.custom_event import MyEvent
from example.custom_router import MyRouter
from example.custom_handler_manager import HandlerProtocol
from eventry.asyncio.callable_wrappers import CallableWrapper


r = MyRouter(router_id='router')


def my_filter() -> bool:
    return False


@r.on_my_event(filter=my_filter)
def my_handler(e: MyEvent) -> Any:
    print(e.object)


@r.on_my_event
def my_event_handler(e: MyEvent) -> Any:
    print(f'2, {e.object}')

