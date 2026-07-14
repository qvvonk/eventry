from .router import Router
from typing import Any
from eventry.event import Event


class Dispatcher:
    _router: Router | None = None

    def __init__(
        self,
        router: Router,
        event_context: dict[str, Any] | None = None,
    ) -> None:
        self.router = router
        self._event_context = event_context or {}

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

    async def propagate_event(
        self,
        event: Event,
        *,
        router: Router | None = None,
        additional_context: dict[str, Any] | None = None
    ) -> None:
        router = router if router is not None else self.router
        if router is None:
            raise ValueError('Router is not set.')

        context = self.event_context | event.dependencies_injection | (additional_context or {})
        await router.propagate_event(event, context)
