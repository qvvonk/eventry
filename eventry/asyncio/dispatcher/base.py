from __future__ import annotations


__all__ = ['Dispatcher']

import asyncio
from collections.abc import Callable

from typing_extensions import TYPE_CHECKING, Any

from eventry.config import DispatcherConfig
from eventry.loggers import dispatcher_logger
from eventry.asyncio.event import Event
from eventry.asyncio.router import Router
from functools import partial


if TYPE_CHECKING:
    pass


class Dispatcher(Router):
    def __init__(
        self,
        error_event_factory: Callable[[Event, Exception], Event],
        workflow_data: dict[str, Any] | None = None,
        config: DispatcherConfig | None = None,
    ) -> None:
        Router.__init__(self, name='Dispatcher')

        self._workflow_data = workflow_data if workflow_data is not None else {}
        self._config = config or DispatcherConfig()
        self._error_event_factory: Callable[[Event, Exception], Event] = error_event_factory

    async def event_entry(
        self,
        event: Event,
        event_context_injection: dict[str, Any] | None = None,
        silent: bool = False,
    ) -> None:
        dispatcher_logger.debug(f'New event %s: %s', event.name, id(event))

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

        async for task_or_exception in self.propagate_event(
            self._config,
            event,
            event_context,
            silent
        ):
            if isinstance(task_or_exception, asyncio.Task):
                task_or_exception.add_done_callback(
                    partial(self._task_done_callback_wrapped, event, silent)
                )
                continue
            if silent:
                continue

            try:
                error_event = self._error_event_factory(event, task_or_exception)
            except:
                dispatcher_logger.error(
                    f'An error occurred while creating error event.',
                    exc_info=True
                )
                continue

            await self.event_entry(error_event, silent=True)

    async def _task_done_callback(
        self,
        event: Event,
        silent: bool,
        task: asyncio.Task[Any]
    ) -> None:
        try:
            task.result()
            event.__handled__ = True
        except Exception as e:
            if not silent:
                await self._propagate_error_event(event, e)

    def _task_done_callback_wrapped(
        self,
        event: Event,
        silent: bool,
        task: asyncio.Task[Any]
    ) -> None:
        asyncio.create_task(self._task_done_callback(event, silent, task))

    async def _propagate_error_event(self, event: Event, exception: Exception) -> None:
        try:
            error_event = self._error_event_factory(event, exception)
        except:
            dispatcher_logger.error(
                f'An error occurred while creating error event.',
                exc_info=True
            )
            return

        await self.event_entry(error_event, silent=True)
        if not error_event.__handled__:
            dispatcher_logger.error(
                f'An error occurred while propagating event %s.', id(event), exc_info=True
            )
