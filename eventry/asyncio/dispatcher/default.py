from __future__ import annotations


__all__ = ['DefaultDispatcher', 'ErrorEvent']


from typing_extensions import Any

from eventry.asyncio.event import ExtendedEvent
from eventry.asyncio.router import DefaultRouter

from .base import Dispatcher


class ErrorEvent(ExtendedEvent):
    def __init__(self, exception: Exception) -> None:
        super().__init__()
        self._exception = exception

    @property
    def exception(self) -> Exception:
        return self._exception

    @property
    def event_context_injection(self) -> dict[str, Any]:
        return {
            'exception': self._exception,
        }


def error_event_factory(exception: Exception) -> ErrorEvent:
    return ErrorEvent(exception)


class DefaultDispatcher(Dispatcher, DefaultRouter):
    def __init__(self, workflow_data: dict[str, Any] | None = None):
        Dispatcher.__init__(
            self,
            error_event_factory=error_event_factory,
            workflow_data=workflow_data,
        )
        DefaultRouter.__init__(self, name='Dispatcher')
