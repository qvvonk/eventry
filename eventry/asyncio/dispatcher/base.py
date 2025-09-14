from __future__ import annotations


__all__ = ('Dispatcher',)


import time
import asyncio
from typing import TYPE_CHECKING, Any
from itertools import chain
from collections.abc import Iterable

from eventry.config import DispatcherConfig
from eventry.loggers import dispatcher_logger
from eventry.asyncio.event import Event, ErrorEvent
from eventry.asyncio.router import Router
from eventry.asyncio.handler_manager import MiddlewareManagerTypes
from eventry.asyncio.middleware_manager import (
    MiddlewareManager,
    WrappedWithMiddlewaresCallable,
)


if TYPE_CHECKING:
    from eventry.asyncio.callable_wrappers import Handler, CallableWrapper


class Dispatcher(Router):
    def __init__(
        self, workflow_data: dict[str, Any] | None = None, config: DispatcherConfig | None = None
    ) -> None:
        super().__init__(router_id='Dispatcher')

        self._workflow_data = workflow_data or {}
        self._config = config or DispatcherConfig()

    async def propagate_event(
        self, event: Event, workflow_injection: dict[str, Any] | None = None, silent: bool = False
    ) -> None:
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

        async for handler, e in self._get_matching_handlers(
            event, self._config.single_handler_mode, data
        ):
            if e is not None:
                dispatcher_logger.debug(
                    f'({id(event)}) An error occurred while executing '
                    f"handler '{handler.id}' filter.",
                    exc_info=e,
                )

                if silent:
                    continue
                await self.propagate_event(ErrorEvent(e), workflow_injection={}, silent=True)
                continue

            await self._execute_handler_wrapper(event, handler, data, silent)

            if event.propagation_stopped:
                dispatcher_logger.debug(f'({id(event)}) Event propagation stopped.')
                break

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
                await self.propagate_event(ErrorEvent(e), workflow_injection={}, silent=True)
            return False

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
