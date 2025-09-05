from __future__ import annotations


__all__ = ['Dispatcher']


import time
import asyncio
from typing import TYPE_CHECKING, Any

from eventry.loggers import router_logger
from eventry.asyncio.bases import MiddlewareCallableType
from eventry.asyncio.middleware_manager import (
    MiddlewareManager,
    WrappedWithMiddlewaresCallable,
)
from eventry.asyncio.router import Router
from eventry.config import DispatcherConfig


if TYPE_CHECKING:
    from eventry.asyncio.bases import HandlerInfo
    from eventry.asyncio.event import Event


class Dispatcher(Router):
    def __init__(
        self,
        workflow_data: dict[str, Any] | None = None,
        config: DispatcherConfig | None = None
    ) -> None:
        super().__init__(name='Dispatcher')

        self._workflow_data = workflow_data or {}
        self._config: DispatcherConfig = config or DispatcherConfig()

    async def propagate_event(
        self,
        event: Event[Any],
    ) -> None:
        router_logger.debug(f'New event {id(event)}: {type(event)}')

        workflow_data = {
            **self._workflow_data,
            **event.workflow_dict,
            'event': event,
            'dispatcher': self,
        }

        executed_handlers: dict[str, bool] = {}
        awaiting_handlers: list[HandlerInfo] = []

        async for handler, e in self.get_matching_handlers(event, workflow_data=workflow_data):
            if e is not None:
                # todo: err event
                router_logger.debug(
                    f'({id(event)}) An error occurred while executing '
                    f"handler '{handler.name}' filters.",
                    exc_info=e,
                )
                continue

            if not handler.can_be_executed(executed_handlers):
                router_logger.debug(
                    f"{id(event)} Execution of handler '{handler.name}'"
                    f' delayed because of `ensure_after`.',
                )
                awaiting_handlers.append(handler)
                continue

            r = await self.execute_handler(event, handler, workflow_data=workflow_data)
            executed_handlers[handler.name] = r

            if event.propagation_stopped:
                router_logger.debug(f'({id(event)}) Event propagation stopped.')
                break

            while True:
                for awaiting_handler in awaiting_handlers:
                    if not awaiting_handler.can_be_executed(executed_handlers):
                        continue

                    awaiting_handlers.remove(awaiting_handler)
                    r = await self.execute_handler(event, awaiting_handler, workflow_data)
                    executed_handlers[awaiting_handler.name] = r
                    break
                else:
                    break

    async def execute_handler(
        self,
        event: Event[Any],
        handler: HandlerInfo,
        workflow_data: dict[str, Any],
    ) -> bool:
        workflow_data = {
            **workflow_data,
            'handler_info': handler,
        }

        wrapped_handler = self._wrap_handler_with_middlewares(
            handler=handler,
            event=event,
            workflow_data=workflow_data,
        )

        router_logger.debug(f"({id(event)}) Executing handler '{handler.name}'...")
        start = time.time()
        result = True
        try:
            if not handler.as_task:
                await wrapped_handler()
            else:
                asyncio.create_task(wrapped_handler())
        except Exception as e:
            router_logger.debug(
                f"({id(event)}) An error occurred while executing handler '{handler.name}'.",
                exc_info=e,
            )
            # todo: exception
            result = False
        finally:
            router_logger.debug(
                f"({id(event)}) Handler '{handler.name}' executed in {time.time() - start} seconds.",
            )
        return result

    def _wrap_handler_with_middlewares(
        self,
        handler: HandlerInfo,
        event: Event[Any],
        workflow_data: dict[str, Any],
    ) -> WrappedWithMiddlewaresCallable:
        pre_execution_middlewares: list[MiddlewareCallableType] = list(
            reversed(handler.middlewares),
        )

        for router in handler.manager.router.chain_to_root_router:
            manager = router.get_manager_by_event(event)
            pre_execution_middlewares.extend(reversed(manager.handler_middlewares))

        handler_with_pre_middlewares = MiddlewareManager.wrap_callable_with_middlewares(
            middlewares=pre_execution_middlewares,
            callable_to_wrap=handler.callable,
            workflow_data=workflow_data,
            first_to_last=False,
        )

        return handler_with_pre_middlewares

    def prepare_kwargs(self, kwargs: dict[str, Any]):
        for old_name, new_name in self.config.builtin_names_remap:
            if old_name in kwargs:
                kwargs[new_name] = kwargs[old_name]
                del kwargs[old_name]

        for excluded_name in self.config.exclude:
            if excluded_name in kwargs:
                del kwargs[excluded_name]

    def prepare_positional_only_args(self, kwargs: dict[str, Any]) -> list[Any]:
        return [v for i, v in kwargs.items() if v in self.config('positional_only_args', [])]
        # todo: exception?

    @property
    def config(self) -> DispatcherConfig:
        return self._config