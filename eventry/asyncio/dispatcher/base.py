from __future__ import annotations


__all__ = ['Dispatcher', 'ErrorContext']


from dataclasses import dataclass
from collections.abc import Callable
from functools import cmp_to_key

from typing_extensions import TYPE_CHECKING, Any

from eventry.config import DispatcherConfig
from eventry.loggers import dispatcher_logger
from eventry.asyncio.event import Event
from eventry.asyncio.router import Router


if TYPE_CHECKING:
    from eventry.asyncio.callable_wrappers import Handler


class Dispatcher(Router):
    def __init__(
        self,
        error_event_factory: Callable[[Exception], Event],
        workflow_data: dict[str, Any] | None = None,
        config: DispatcherConfig | None = None,
    ) -> None:
        Router.__init__(self, name='Dispatcher')

        self._workflow_data = workflow_data if workflow_data is not None else {}
        self._config = config or DispatcherConfig()
        self._error_event_factory: Callable[[Exception], Event] = error_event_factory

    async def event_entry(
        self,
        event: Event,
        event_context_injection: dict[str, Any] | None = None,
        silent: bool = False,
    ) -> None:
        dispatcher_logger.debug(f'New event {id(event)}: {type(event)}')

        if event_context_injection is None:
            event_context_injection = {}

        event_context: dict[str, Any] = {
            **self._workflow_data,
            **event.event_context_injection,
            **event_context_injection,
            self._config.default_names_remap.get('event', 'event'): event,
            self._config.default_names_remap.get('dispatcher', 'dispatcher'): self,
        }
        event_context[self._config.default_names_remap.get('data', 'data')] = event_context

        async for exception in self.propagate_event(self._config, event, event_context, silent):
            if silent:
                continue

            try:
                error_event = self._error_event_factory(exception)
            except Exception as e:
                dispatcher_logger.error(f'An error occurred while creating error event: {e}')
                continue

            await self.event_entry(error_event, silent=True)
