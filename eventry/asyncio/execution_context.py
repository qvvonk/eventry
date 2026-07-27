from __future__ import annotations


__all__ = [
    'ExecutionContext',
    'RouterExecutionContext',
    'ManagerExecutionContext',
    'HandlerExecutionContext',
]


from typing import TYPE_CHECKING, Any
from dataclasses import dataclass


if TYPE_CHECKING:
    from eventry.asyncio.event import Event
    from eventry.asyncio.router import Router
    from eventry.asyncio.dispatcher import Dispatcher
    from eventry.asyncio.handler_manager import HandlerManager
    from eventry.asyncio.callable_wrappers import Handler


@dataclass(kw_only=True)
class ExecutionContext:
    event: Event
    dispatcher: 'Dispatcher'
    context: dict[str, Any]

    def shallow_asdict(self) -> dict[str, Any]:
        return {
            f.name: self.__dict__[f.name]
            for f in type(self).__dict__['__dataclass_fields__'].values()
        }


@dataclass(kw_only=True)
class RouterExecutionContext(ExecutionContext):
    router: Router


@dataclass(kw_only=True)
class ManagerExecutionContext(RouterExecutionContext):
    manager: HandlerManager


@dataclass(kw_only=True)
class HandlerExecutionContext(ManagerExecutionContext):
    handler: Handler[Any]
