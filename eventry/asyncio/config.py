from __future__ import annotations


__all__ = [
    'RouterConfig',
    'HandlerManagerConfig',
    'EventDispatchingConfig',
    'default_error_callback',
    'default_handler_callback',
    'Context',
    'FromContext',
]

from typing import Any
from dataclasses import dataclass
from collections.abc import Callable, Awaitable

from eventry._config import RouterConfig, HandlerManagerConfig
from eventry.loggers import logger
from eventry._argument_sources import Context, FromContext
from eventry.asyncio.dispatching_context import DispatchingContext


async def default_error_callback(ctx: DispatchingContext, exc: Exception) -> None:
    if ctx.handler is not None and ctx.manager is not None:
        logger.error(
            f'An error occurred while executing handler '
            f'{ctx.handler.name!r} @ {ctx.manager.name!r} @ {ctx.router.full_name}.'
            f'for event {ctx.event.name!r}.',
            exc_info=exc,
        )
    elif ctx.manager is not None:
        logger.error(
            f'An error occurred while executing handlers of manager '
            f'{ctx.manager.name!r} @ {ctx.router.full_name}.',
            exc_info=exc,
        )
    elif ctx.router is not None:
        logger.error(
            f'An error occurred while executing handlers of router {ctx.router.full_name}.',
            exc_info=exc,
        )


async def default_handler_callback(*_: Any) -> None:
    return


@dataclass(kw_only=True)
class EventDispatchingConfig:
    on_error: Callable[[DispatchingContext, Exception], Awaitable[Any]] = default_error_callback
    on_handler: Callable[[DispatchingContext, Any], Awaitable[Any]] = default_handler_callback
