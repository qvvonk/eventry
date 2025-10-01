from __future__ import annotations


__all__ = ['Dispatcher', 'ErrorContext']


import time
import asyncio
from typing_extensions import TYPE_CHECKING, Any
from dataclasses import dataclass
from itertools import chain
from collections.abc import Callable, Iterable

from eventry.config import DispatcherConfig
from eventry.loggers import dispatcher_logger
from eventry.exceptions import FinalizingError, Finalized
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
        Router.__init__(self, name='Dispatcher')

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

        for router in self.chain_to_last_router:
            if event.propagation_stopped:
                return

            manager = router[event]
            global_middlewares = manager.middleware_manager(MiddlewareManagerTypes.GLOBAL) or []

            wrapped: MiddlewareWrappedCallable[None] = (
                MiddlewareWrappedCallable(
                    self._execute_manager_handlers,
                    middlewares=global_middlewares,
                )
            )

            try:
                await wrapped(
                    callable_args=(event, manager, event_context, silent),
                    middlewares_args=manager.config.middleware_positional_only_args,
                    data=event_context,
                    executor=executor,
                    finalize=False,
                )
            except Finalized:
                return
            except Exception as e:
                if isinstance(e, FinalizingError):
                    e = e.__cause__
                if not silent:
                    err_event = self._error_event_factory(ErrorContext(e, None, event))
                    await self.propagate_event(err_event, {}, silent=True)
                return

            outer = manager.middleware_manager(MiddlewareManagerTypes.OUTER_PER_HANDLER)
            inner = manager.middleware_manager(MiddlewareManagerTypes.INNER_PER_HANDLER)
            event.__inherited_outer_middlewares__.extend(
                outer.inheritable_middlewares if outer is not None else []
            )
            event.__inherited_inner_middlewares__.extend(
                 inner.inheritable_middlewares if inner is not None else []
            )

        try:
            await executor.finalize_middlewares()
        except Exception as e:
            if not silent:
                err_event = self._error_event_factory(ErrorContext(e, None, event))
                await self.propagate_event(err_event, {}, silent=True)

    async def _execute_manager_handlers(
        self,
        event: Event,
        manager: HandlerManager[Any, Any, Any, Any],
        event_context: dict[str, Any],
        silent: bool,
    ) -> None:
        async for h in manager.get_matching_handlers(event):
            event_context = {
                **event_context,
                self._config.default_names_remap.get('handler', 'handler'): h
            }
            event_context[self._config.default_names_remap.get('data', 'data')] = event_context

            try:
                await self._execute_handler(event, h, event_context=event_context)
            except Exception as e:
                if isinstance(e, FinalizingError):
                    e = e.__cause__
                if not silent:
                    err_event = self._error_event_factory(ErrorContext(e, h, event))
                    await self.propagate_event(err_event, {}, silent=True)

            if event.propagation_stopped:
                dispatcher_logger.debug(f'({id(event)}) Event propagation stopped.')
                break

    async def _execute_handler(
        self,
        event: Event,
        handler: Handler[Any],
        event_context: dict[str, Any],
    ) -> Any:
        dispatcher_logger.debug(
            f'({id(event)}) Executing handler '
            f'{handler.manager.router.name} -> {handler.manager.id} -> {handler.id}...',
        )

        start = time.time()
        try:
            if not handler.as_task:
                return await handler.execute_wrapped(
                    data=event_context,
                    inherited_outer_middlewares=event.__inherited_outer_middlewares__,
                    inherited_inner_middlewares=event.__inherited_inner_middlewares__,
                )
            else:
                asyncio.create_task(
                    handler.execute_wrapped(
                        data=event_context,
                        inherited_outer_middlewares=event.__inherited_outer_middlewares__,
                        inherited_inner_middlewares=event.__inherited_inner_middlewares__,
                    )
                )
        except Exception as e:
            if isinstance(e, FinalizingError):
                e = e.__cause__
            dispatcher_logger.debug(
                f'({id(event)}) An error occurred while executing handler '
                f'{handler.manager.router.name} -> {handler.manager.id} -> {handler.id}.',
                exc_info=e,
            )
            raise e
        finally:
            dispatcher_logger.debug(
                f"({id(event)}) Handler '{handler.id}' executed in {time.time() - start} seconds.",
            )
