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
from eventry.asyncio.handler_manager import MiddlewareManagerTypes
from eventry.asyncio.middleware_manager import (
    MiddlewaresExecutionState,
    WrappedWithMiddlewaresCallable,
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

        self._workflow_data = workflow_data or {}
        self._config = config or DispatcherConfig()
        self._error_event_factory: Callable[[ErrorContext], Event] = error_event_factory

    async def propagate_event(
        self,
        event: Event,
        workflow_injection: dict[str, Any] | None = None,
        silent: bool = False,
    ) -> None:
        dispatcher_logger.debug(f'New event {id(event)}: {type(event)}')

        workflow_injection = workflow_injection or {}
        executed_handlers: dict[str, tuple[Handler[Any], Any]] = {}

        data: dict[str, Any] = {
            **self._workflow_data,
            **workflow_injection,
            **event.workflow_injection,
            self._config.default_names_remap.get(
                'executed_handlers',
                'executed_handlers',
            ): executed_handlers,
            self._config.default_names_remap.get('event', 'event'): event,
            self._config.default_names_remap.get('dispatcher', 'dispatcher'): self,
        }
        data[self._config.default_names_remap.get('data', 'data')] = data

        errors: list[ErrorContext] = []
        state = MiddlewaresExecutionState()
        execution_aborted = False

        for manager in self._get_handler_managers_to_tail(event):
            outer_middlewares = manager.middleware_manager(MiddlewareManagerTypes.OUTER)
            if not outer_middlewares:
                errors.extend(await self._execute_manager_handlers(event, manager, data, silent))
                continue

            state.add_middlewares(*outer_middlewares)
            wrapped: WrappedWithMiddlewaresCallable[list[ErrorContext]] = (
                WrappedWithMiddlewaresCallable(
                    self._execute_manager_handlers,
                    middlewares=outer_middlewares,
                )
            )

            try:
                result = await wrapped(
                    callable_positional_only_args=(event, manager, data, silent),
                    middlewares_positional_only_args=manager.config.middleware_positional_only_args,
                    data=data,
                    state=state,
                    execute_after_part=False,
                )
                errors.extend(result)
            except HandlerNotExecuted:
                execution_aborted = True
                break

        if not execution_aborted:
            try:
                await state.execute_after_part()
            except Exception as e:
                errors.append(ErrorContext(exception=e, handler=None, event=event))

        for err in errors:
            event = self._error_event_factory(err)
            await self.propagate_event(event, {}, silent=True)

    async def _execute_manager_handlers(
        self,
        event: Event,
        manager: HandlerManager[Any, Any, Any, Any],
        data: dict[str, Any],
        silent: bool,
    ) -> list[ErrorContext]:
        errors: list[ErrorContext] = []

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
                    errors.append(ErrorContext(e, handler, event))
                continue

            result = await self._execute_handler_wrapper(event, handler, data, silent)
            if isinstance(result, ErrorContext):
                errors.append(result)

            if event.propagation_stopped:
                dispatcher_logger.debug(f'({id(event)}) Event propagation stopped.')
                break
        return errors

    async def _execute_handler_wrapper(
        self,
        event: Event,
        handler: Handler[Any],
        data: dict[str, Any],
        silent: bool,
    ) -> Any:
        try:
            return await self._execute_handler(event, handler, data=data)
        except HandlerNotExecuted:
            raise
        except Exception as e:
            if not silent:
                return ErrorContext(e, handler, event)

    async def _execute_handler(
        self,
        event: Event,
        handler: Handler[Any],
        data: dict[str, Any],
    ) -> Any:
        data[self._config.default_names_remap.get('handler', 'handler')] = handler

        wrapped_handler = self._wrap_handler_with_middlewares(
            handler=handler,
            event=event,
        )

        dispatcher_logger.debug(
            f'({id(event)}) Executing handler '
            f'{handler.manager.router.id} -> {handler.manager.id} -> {handler.id}...',
        )
        start = time.time()
        try:
            if not handler.as_task:
                return await wrapped_handler(
                    callable_positional_only_args=handler.manager.config.handler_positional_only_args,
                    middlewares_positional_only_args=handler.manager.config.middleware_positional_only_args,
                    data=data,
                )
            asyncio.create_task(
                wrapped_handler(
                    callable_positional_only_args=handler.manager.config.handler_positional_only_args,
                    middlewares_positional_only_args=handler.manager.config.middleware_positional_only_args,
                    data=data,
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

    def _wrap_handler_with_middlewares(
        self,
        handler: Handler[Any],
        event: Event,
    ) -> WrappedWithMiddlewaresCallable[Any]:
        middlewares: list[Iterable[CallableWrapper[Any]]] = (
            [handler.middlewares] if handler.middlewares else []
        )

        if handler.manager.middleware_manager(MiddlewareManagerTypes.INNER):
            for router in handler.manager.router.chain_to_root_router:
                manager = router._get_handler_manager(event)
                middlewares.append(manager.middleware_manager(MiddlewareManagerTypes.INNER))

        return WrappedWithMiddlewaresCallable(
            handler._callable,
            middlewares=chain(*reversed(middlewares)),
        )
