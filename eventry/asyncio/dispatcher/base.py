from __future__ import annotations


__all__ = ['Dispatcher', 'ErrorContext']


import time
import asyncio
from dataclasses import dataclass
from collections.abc import Callable

from typing_extensions import TYPE_CHECKING, Any

from eventry.config import DispatcherConfig
from eventry.loggers import dispatcher_logger
from eventry.exceptions import _EarlyFinalized, FinalizingError, _SkipRouter, _ManagerFilterError
from eventry.asyncio.event import Event
from eventry.asyncio.router import Router
from eventry.asyncio.middleware_manager import (
    MiddlewaresExecutor,
    MiddlewareManagerTypes,
    MiddlewareWrappedCallable,
)

if TYPE_CHECKING:
    from eventry.asyncio.handler_manager import HandlerManager
    from eventry.asyncio.callable_wrappers import Handler


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

        if event_context_injection is None:
            event_context_injection = {}

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

        global_middlewares_executor = MiddlewaresExecutor()
        routers_gen = self.chain_to_tails
        curr_router = next(routers_gen)
        exc_to_global_finalizers = None

        while True:
            if event.propagation_stopped:
                break

            skip = False

            try:
                await self._propagate_event_iteration(
                    event,
                    curr_router,
                    event_context,
                    silent,
                    global_middlewares_executor
                )
            except _SkipRouter:
                skip = True
            except _ManagerFilterError as e:
                exc_to_global_finalizers = e.__cause__
                break

            try:
                curr_router = routers_gen.send(skip)
            except StopIteration:
                break

        try:
            await global_middlewares_executor.finalize_middlewares(
                exception=exc_to_global_finalizers
            )
        except Exception as e:
            if not silent:
                err_event = self._error_event_factory(ErrorContext(e, None, event))
                await self.propagate_event(err_event, {}, silent=True)

    async def _propagate_event_iteration(
        self,
        event: Event,
        router: Router,
        event_context: dict[str, Any],
        silent: bool,
        global_middlewares_executor: MiddlewaresExecutor
    ):
        manager = router[event]
        global_middlewares = manager.middleware_manager(MiddlewareManagerTypes.GLOBAL) or []

        wrapped: MiddlewareWrappedCallable[None] = MiddlewareWrappedCallable(
            self._execute_manager_handlers,
            middlewares=global_middlewares,
        )

        try:
            await wrapped(
                callable_args=(event, manager, event_context, silent),
                middlewares_args=manager.config.middleware_positional_only_args,
                data=event_context,
                executor=global_middlewares_executor,
                finalize_on_callable_exception=False,
                finalize=False,
            )
        except (_SkipRouter, _ManagerFilterError):
            raise
        except _EarlyFinalized:
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
            outer.inheritable_middlewares if outer is not None else [],
        )
        event.__inherited_inner_middlewares__.extend(
            inner.inheritable_middlewares if inner is not None else [],
        )

    async def _execute_manager_handlers(
        self,
        event: Event,
        manager: HandlerManager[Any, Any, Any, Any],
        event_context: dict[str, Any],
        silent: bool,
    ) -> None:
        """
        Executes passed manager's filter and handlers.
        If an exception occurred in the manager's filter, raises `_ManagerFilterError`.
        with the original exception in `__cause__`.
        # todo: log error? config?

        If any unhandled exception occurred and `silent` is False - generates and propagates a
        new error event.
        If `silent` is True - ignores the error.  # todo: log error
        """
        if manager.filter:
            try:
                filter_result = await manager.filter.execute(
                    manager._config.filter_positional_only_args,
                    event_context
                )
            except Exception as e:
                new_e =  _ManagerFilterError()
                new_e.__cause__ = e
                raise new_e
            if not filter_result:
                # todo: logging
                raise _SkipRouter

        async for h in manager.get_matching_handlers(event):
            event_context = {
                **event_context,
                self._config.default_names_remap.get('handler', 'handler'): h,
            }
            event_context[self._config.default_names_remap.get('data', 'data')] = event_context

            try:
                await self._execute_handler(event, h, event_context=event_context)
            except Exception as e:
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
        """
        Executes handler with filter and outer-inner-handler middlewares.
        If an unhandled in middlewares error occurred - raises it.
        """
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
            asyncio.create_task(
                handler.execute_wrapped(
                    data=event_context,
                    inherited_outer_middlewares=event.__inherited_outer_middlewares__,
                    inherited_inner_middlewares=event.__inherited_inner_middlewares__,
                ),
            )
        except Exception as e:
            if isinstance(e, FinalizingError):
                e = e.__cause__
            dispatcher_logger.error(
                f'({id(event)}) An error occurred while executing handler '
                f'{handler.manager.router.name} -> {handler.manager.id} -> {handler.id}.',
                exc_info=e,
            )
            raise e
        finally:
            dispatcher_logger.debug(
                f"({id(event)}) Handler '{handler.id}' executed in {time.time() - start} seconds.",
            )
