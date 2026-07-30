from __future__ import annotations


__all__ = [
    'Dispatcher',
    'EventDispatchingConfig',
]


from typing import Any

from eventry.asyncio.event import Event
from eventry.asyncio.config import EventDispatchingConfig
from eventry.asyncio.router.base import Router
from eventry.asyncio.dispatching_context import DispatchingContext


class Dispatcher:
    _router: Router[Any] | None = None

    def __init__(
        self,
        router: Router[Any] | None = None,
        event_context: dict[str, Any] | None = None,
        config: EventDispatchingConfig | None = None,
    ) -> None:
        self.router = router
        self._event_context = event_context or {}
        self._config = config if config is not None else EventDispatchingConfig()

    @property
    def router(self) -> Router[Any] | None:
        return self._router

    @router.setter
    def router(self, router: Router[Any] | None) -> None:
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
        router: Router[Any] | None = None,
        additional_context: dict[str, Any] | None = None,
        config: EventDispatchingConfig | None = None,
    ) -> None:
        if not isinstance(event, Event):
            raise TypeError(
                f'Event must be an instance of Event, not {event.__class__.__name__!r}.',
            )

        router = router if router is not None else self.router
        if router is None:
            raise ValueError('Router is not set.')

        config = config if config is not None else self.config
        context = DispatchingContext(
            dispatcher=self,
            router=router,
            event=event,
            data={**self.event_context, **event.context_injection(), **(additional_context or {})},
        )
        await router.propagate_event(config, context)

    def __repr__(self) -> str:
        return f'Dispatcher({self.router!r})'
