from __future__ import annotations


__all__ = ['DefaultDispatcher', 'ErrorEvent']


from typing import Any

from eventry.asyncio.event import ExtendedEvent
from eventry.asyncio.router import DefaultRouter

from .base import Dispatcher, ErrorContext


class ErrorEvent(ExtendedEvent):
    def __init__(self, context: ErrorContext) -> None:
        super().__init__()
        self._context = context

    @property
    def context(self) -> ErrorContext:
        return self._context

    @property
    def workflow_injection(self) -> dict[str, Any]:
        return {'context': self.context}


def error_event_factory(context: ErrorContext) -> ErrorEvent:
    return ErrorEvent(context)


class DefaultDispatcher(Dispatcher, DefaultRouter):
    def __init__(self, workflow_data: dict[str, Any] | None = None):
        Dispatcher.__init__(
            self, error_event_factory=error_event_factory, workflow_data=workflow_data
        )
        DefaultRouter.__init__(self, router_id='Dispatcher')
