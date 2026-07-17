from __future__ import annotations


__all__ = [
    'ExecutionContext',
    'RouterExecutionContext',
    'ManagerExecutionContext',
    'HandlerExecutionContext',
]


from dataclasses import dataclass

from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from eventry.event import Event
    from eventry.asyncio.dispatcher import Dispatcher
    from eventry.asyncio.handler_manager import HandlerManager
    from eventry.asyncio.router import Router
    from eventry.asyncio.callable_wrappers import Handler


@dataclass(kw_only=True)
class ExecutionContext:
    event: Event
    dispatcher: 'Dispatcher'
    context: dict[str, Any]
    exception: Exception | None = None


@dataclass(kw_only=True)
class RouterExecutionContext(ExecutionContext):
    router: Router


@dataclass(kw_only=True)
class ManagerExecutionContext(RouterExecutionContext,):
    manager: HandlerManager


@dataclass(kw_only=True)
class HandlerExecutionContext(ManagerExecutionContext):
    handler: Handler[Any]