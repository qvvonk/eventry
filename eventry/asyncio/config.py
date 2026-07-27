from __future__ import annotations


__all__ = [
    'RouterConfig',
    'HandlerManagerConfig',
    'EventDispatchingConfig',
    'default_error_callback',
    'default_handler_callback',
    'Kwargs',
    'FromKwargs',
]

from typing import Any
from dataclasses import dataclass
from collections.abc import Callable, Awaitable

from eventry._config import RouterConfig, HandlerManagerConfig
from eventry.loggers import logger
from eventry._argument_sources import Kwargs, FromKwargs
from eventry.asyncio.execution_context import (
    RouterExecutionContext,
    HandlerExecutionContext,
    ManagerExecutionContext,
)


async def default_error_callback(ctx: RouterExecutionContext, exc: Exception) -> None:
    if not isinstance(ctx, RouterExecutionContext):
        return

    if isinstance(ctx, HandlerExecutionContext):
        logger.error(
            f'An error occurred while executing handler {ctx.handler.id!r} @ {ctx.manager.name!r} @ {ctx.router.full_name}'
            f'for event {ctx.event.name!r}.',
            exc_info=exc,
        )
    elif isinstance(ctx, ManagerExecutionContext):
        logger.error(
            f'An error occurred while executing handlers of manager {ctx.manager.name!r} @ {ctx.router.full_name}.',
            exc_info=exc,
        )
    else:
        logger.error(
            f'An error occurred while executing handlers of router {ctx.router.full_name}.',
            exc_info=exc,
        )


async def default_handler_callback(*_: Any) -> None:
    return


@dataclass(kw_only=True)
class EventDispatchingConfig:
    on_error: Callable[[RouterExecutionContext, Exception], Awaitable[Any]] = (
        default_error_callback
    )
    on_handler: Callable[[HandlerExecutionContext, Any], Awaitable[Any]] = default_handler_callback
