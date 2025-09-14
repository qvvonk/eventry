from __future__ import annotations


__all__ = ['Dispatcher', 'ErrorContext']


import time
import asyncio
from typing import TYPE_CHECKING, Any
from itertools import chain
from collections.abc import Iterable

from eventry.config import DispatcherConfig
from eventry.loggers import dispatcher_logger
from eventry.asyncio.event import Event
from eventry.asyncio.router import Router
from eventry.asyncio.handler_manager import MiddlewareManagerTypes
from eventry.asyncio.middleware_manager import (
    MiddlewareManager,
    WrappedWithMiddlewaresCallable,
)
from collections.abc import Callable
from dataclasses import dataclass

if TYPE_CHECKING:
    from eventry.asyncio.callable_wrappers import Handler, CallableWrapper
    from eventry.asyncio.handler_manager import HandlerManager


@dataclass(frozen=True)
class ErrorContext:
    exception: Exception
    handler: Handler[Any]
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

    async def propagate_event(self, event: Event, workflow_injection: dict[str, Any] | None = None, silent: bool = False) -> None:
        dispatcher_logger.debug(f'New event {id(event)}: {type(event)}')

        workflow_injection = workflow_injection or {}

        data = {
            **self._workflow_data,
            **workflow_injection,
            **event.workflow_injection,
            'event': event,
            'dispatcher': self,
        }
        data['data'] = data
        errors: list[ErrorContext]= []

        for manager in self._get_handler_managers_to_tail(event):
            outer_middlewares = manager.middleware_manager(MiddlewareManagerTypes.OUTER)
            if outer_middlewares:
                wrapped: WrappedWithMiddlewaresCallable[Any] = outer_middlewares.wrap_callable_with_middlewares(
                    self._execute_manager_handlers,
                    middlewares=outer_middlewares,
                    data=data,
                    callable_positional_only_args=(event, manager, data, silent),
                    middlewares_positional_only_args=manager._config.middleware_positional_only_args,
                )
                state = await wrapped()
                if not state.callable_executed:
                    return
                else:
                    result = state.callable_return
            else:
                result = await self._execute_manager_handlers(event, manager, data, silent)

            errors.extend(result)

        for err in errors:
            event = self._error_event_factory(err)
            await self.propagate_event(event, {}, silent=True)

    async def _execute_manager_handlers(
        self,
        event: Event,
        manager: HandlerManager[Any, Any, Any, Any],
        data: dict[str, Any],
        silent: bool
    ) -> list[ErrorContext]:
        errors: list[ErrorContext] = []

        async for handler, e in manager.get_matching_handlers(
            event, self._config.single_handler_mode, data
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
            r = await self._execute_handler(event, handler, data=data)
            return r
        except Exception as e:
            if not silent:
                return ErrorContext(e, handler, event)

    async def _execute_handler(
        self,
        event: Event,
        handler: Handler[Any],
        data: dict[str, Any],
    ) -> Any:
        data['handler'] = handler

        wrapped_handler = self._wrap_handler_with_middlewares(
            handler=handler,
            event=event,
            workflow_data=data,
        )

        dispatcher_logger.debug(
            f'({id(event)}) Executing handler '
            f'{handler.handler_manager.router.id} -> {handler.handler_manager.id} -> {handler.id}...',
        )
        start = time.time()
        try:
            if not handler.as_task:
                return await wrapped_handler()
            asyncio.create_task(wrapped_handler())
        except Exception as e:
            dispatcher_logger.debug(
                f'({id(event)}) An error occurred while executing handler '
                f'{handler.handler_manager.router.id} -> {handler.handler_manager.id} -> {handler.id}.',
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
        workflow_data: dict[str, Any],
    ) -> WrappedWithMiddlewaresCallable[Any]:
        middlewares: list[Iterable[CallableWrapper[Any]]] = (
            [reversed(handler.middlewares)] if handler.middlewares else []
        )

        if handler.handler_manager.middleware_manager(MiddlewareManagerTypes.INNER):
            for router in handler.handler_manager.router.chain_to_root_router:
                manager = router._get_handler_manager(event)
                middlewares.append(
                    reversed(manager.middleware_manager(MiddlewareManagerTypes.INNER))
                )

        handler_with_pre_middlewares = MiddlewareManager.wrap_callable_with_middlewares(
            handler._callable,
            middlewares=chain(*middlewares),
            data=workflow_data,
            callable_positional_only_args=handler.handler_manager._config.positional_only_args,
            middlewares_positional_only_args=handler.handler_manager._config.middleware_positional_only_args,
            default_names_remap=self._config.default_names_remap,
        )
        return handler_with_pre_middlewares
