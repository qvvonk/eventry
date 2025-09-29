from __future__ import annotations


__all__ = ['Dispatcher', 'ErrorContext']


import time
import asyncio
from typing import TYPE_CHECKING, Any
from dataclasses import dataclass
from itertools import chain
from collections.abc import Callable, Iterable

from eventry.config import DispatcherConfig
from eventry.loggers import dispatcher_logger
from eventry.exceptions import HandlerNotExecuted
from eventry.asyncio.event import Event
from eventry.asyncio.router import Router
from eventry.asyncio.middleware_manager import (
    MiddlewaresExecutor,
    MiddlewareWrappedCallable, MiddlewareManagerTypes,
)


if TYPE_CHECKING:
    from eventry.asyncio.handler_manager import HandlerManager
    from eventry.asyncio.callable_wrappers import Handler, CallableWrapper


@dataclass(frozen=True)
class ErrorContext:
    exception: Exception
    handler: Handler[Any] | None
    event: Event


class Dispatcher(Router):
    def __init__(
        self,
        error_event_factory: Callable[[ErrorContext], Event],
        workflow_data: dict[str, Any] | None = None,
        config: DispatcherConfig | None = None,
    ) -> None:
        Router.__init__(self, router_id='Dispatcher')

        self._workflow_data = workflow_data if workflow_data is not None else {}
        self._config = config or DispatcherConfig()
        self._error_event_factory: Callable[[ErrorContext], Event] = error_event_factory

    async def propagate_event(
        self,
        event: Event,
        event_context_injection: dict[str, Any] | None = None,
        silent: bool = False,
    ) -> None:
        dispatcher_logger.debug(f'New event {id(event)}: {type(event)}')

        event_context_injection = event_context_injection or {}
        executed_handlers: dict[str, tuple[Handler[Any], Any]] = {}

        event_context: dict[str, Any] = {
            **self._workflow_data,
            **event.event_context_injection,
            **event_context_injection,
            self._config.default_names_remap.get(
                'executed_handlers',
                'executed_handlers',
            ): executed_handlers,
            self._config.default_names_remap.get('event', 'event'): event,
            self._config.default_names_remap.get('dispatcher', 'dispatcher'): self,
        }
        event_context[self._config.default_names_remap.get('data', 'data')] = event_context

        executor = MiddlewaresExecutor()
        execution_aborted = False

        for router in self.chain_to_last_router:
            manager = router[event]
            outer_middlewares = manager.middleware_manager(MiddlewareManagerTypes.OUTER)
            if not outer_middlewares:
                await self._execute_manager_handlers(event, manager, event_context, silent)
                continue

            wrapped: MiddlewareWrappedCallable[None] = (
                MiddlewareWrappedCallable(
                    self._execute_manager_handlers,
                    middlewares=outer_middlewares,
                )
            )

            try:
                await wrapped(
                    callable_args=(event, manager, event_context, silent),
                    middlewares_args=manager.config.middleware_positional_only_args,
                    data=event_context,
                    executor=executor,
                    execute_post_middlewares=False,
                )
            except HandlerNotExecuted:
                execution_aborted = True
                break

        if not execution_aborted:
            try:
                await executor.execute_post_middlewares()
            except Exception as e:
                if not silent:
                    err_event = self._error_event_factory(ErrorContext(e, None, event))
                    await self.propagate_event(err_event, {}, silent=True)

    async def _execute_manager_handlers(
        self,
        event: Event,
        manager: HandlerManager[Any, Any, Any, Any],
        data: dict[str, Any],
        silent: bool,
    ) -> None:
        async for handler, e in manager.get_matching_handlers(
            event,
            self._config.single_handler_mode,
            data,
        ):
            if e is not None:
                dispatcher_logger.debug(
                    f'({id(event)}) An error occurred while executing '
                    f"handler '{handler.id}' filter.",
                    exc_info=e,
                )

                if not silent:
                    err_event = self._error_event_factory(ErrorContext(e, handler, event))
                    await self.propagate_event(err_event, {}, silent=True)
                continue

            await self._execute_handler_wrapper(event, handler, data, silent)

            if event.propagation_stopped:
                dispatcher_logger.debug(f'({id(event)}) Event propagation stopped.')
                break

    async def _execute_handler_wrapper(
        self,
        event: Event,
        handler: Handler[Any],
        event_context: dict[str, Any],
        silent: bool,
    ) -> Any:
        # Creating own copy of context for each handler and its inner middlewares.
        event_context = {
            **event_context,
            self._config.default_names_remap.get('handler', 'handler'): handler
        }
        event_context[self._config.default_names_remap.get('data', 'data')] = event_context

        try:
            return await self._execute_handler(event, handler, event_context=event_context)
        except HandlerNotExecuted:
            raise
        except Exception as e:
            if not silent:
                err_event = self._error_event_factory(ErrorContext(e, handler, event))
                await self.propagate_event(err_event, {}, silent=True)

    async def _execute_handler(
        self,
        event: Event,
        handler: Handler[Any],
        event_context: dict[str, Any],
    ) -> Any:
        dispatcher_logger.debug(
            f'({id(event)}) Executing handler '
            f'{handler.manager.router.id} -> {handler.manager.id} -> {handler.id}...',
        )

        start = time.time()
        wrapped_handler = handler.wrap_with_middlewares()
        try:
            if not handler.as_task:
                return await wrapped_handler(
                    callable_args=handler.manager.config.handler_positional_only_args,
                    middlewares_args=handler.manager.config.middleware_positional_only_args,
                    data=event_context,
                )
            asyncio.create_task(
                wrapped_handler(
                    callable_args=handler.manager.config.handler_positional_only_args,
                    middlewares_args=handler.manager.config.middleware_positional_only_args,
                    data=event_context,
                )
            )
        except Exception as e:
            dispatcher_logger.debug(
                f'({id(event)}) An error occurred while executing handler '
                f'{handler.manager.router.id} -> {handler.manager.id} -> {handler.id}.',
                exc_info=e,
            )
            raise e
        finally:
            dispatcher_logger.debug(
                f"({id(event)}) Handler '{handler.id}' executed in {time.time() - start} seconds.",
            )
