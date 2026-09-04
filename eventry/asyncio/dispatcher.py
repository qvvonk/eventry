from __future__ import annotations


__all__ = [
    'Dispatcher',
    'DispatchingConfig',
]

from typing import Any
from types import MappingProxyType
from collections.abc import Mapping

from eventry.asyncio.event import Event
from eventry.asyncio.config import DispatchingConfig
from eventry.asyncio.router.base import Router
from eventry.asyncio.dispatching_context import DispatchingContext


class Dispatcher:
    _router: Router[Any] | None = None

    def __init__(
        self,
        router: Router[Any] | None = None,
        event_context: Mapping[str, Any] | None = None,
        config: DispatchingConfig | None = None,
    ) -> None:
        self.router = router
        self._event_context = event_context if event_context is not None else {}
        self._event_context_proxy = MappingProxyType(self._event_context)
        self._config = config if config is not None else DispatchingConfig()

    @property
    def router(self) -> Router[Any] | None:
        return self._router

    @router.setter
    def router(self, router: Router[Any] | None) -> None:
        if router is not None and not isinstance(router, Router):
            raise TypeError(f'Router must be an instance of Router, not {type(router)!r}.')
        self._router = router

    @property
    def event_context(self) -> Mapping[str, Any]:
        return self._event_context_proxy

    @property
    def config(self) -> DispatchingConfig:
        return self._config

    async def propagate_event(
        self,
        event: Event,
        *,
        router: Router[Any] | None = None,
        additional_context: dict[str, Any] | None = None,
        config: DispatchingConfig | None = None,
    ) -> DispatchingContext:
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
        return context

    def __repr__(self) -> str:
        return f'Dispatcher({self.router!r})'
