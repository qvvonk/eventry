from __future__ import annotations

from .router import Router
from typing import Any
from eventry.event import Event
from eventry._execution_context import ExecutionContext
from eventry._config import AsyncEventDispatchingConfig as EventDispatchingConfig


class Dispatcher:
    _router: Router | None = None

    def __init__(
        self,
        router: Router,
        event_context: dict[str, Any] | None = None,
        config: EventDispatchingConfig | None = None
    ) -> None:
        self.router = router
        self._event_context = event_context or {}
        self._config = config if config is not None else EventDispatchingConfig()

    @property
    def router(self) -> Router | None:
        return self._router

    @router.setter
    def router(self, router: Router | None) -> None:
        if router is not None and not isinstance(router, Router):
            raise TypeError(f'Router must be an instance of Router, not {type(router)!r}.')
        self._router = router

    @property
    def event_context(self) -> dict[str, Any]:
        return self._event_context

    @property
    def config(self) -> EventDispatchingConfig:
        return self._config

    async def propagate_event(
        self,
        event: Event,
        *,
        router: Router | None = None,
        additional_context: dict[str, Any] | None = None,
        config: EventDispatchingConfig | None = None
    ) -> None:
        router = router if router is not None else self.router
        if router is None:
            raise ValueError('Router is not set.')

        config = config if config is not None else self.config
        context = self.event_context | event.dependencies_injection | (additional_context or {})
        execution_context = ExecutionContext(
            event=event,
            dispatcher=self,
            context=context,
            exception=None
        )
        await router.propagate_event(event, config, execution_context, context)
