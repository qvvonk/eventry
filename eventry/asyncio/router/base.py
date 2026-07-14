from __future__ import annotations


__all__ = ['Router']


from typing import TYPE_CHECKING, Any
from copy import copy

if TYPE_CHECKING:
    from eventry.asyncio.handler_manager import HandlerManager
    from eventry.event import Event


class Router:
    def __init__(
        self,
        name: str = '',
    ) -> None:
        self._name = name or self.__class__.__name__
        self._sub_routers: dict[str, Router] = {}
        self._handler_managers: dict[str, HandlerManager] = {}
        self._parent: Router | None = None

    def attach_router(self, router: Router) -> None:
        if router is self:
            raise ValueError('Cannot attach router to itself.')

        if router.parent is not None:
            raise ValueError('Router already has a parent.')

        self._sub_routers[router.name] = router
        router._parent = self
        # todo: add checks

    def remove_subrouter(self, router: str | Router) -> Router:
        name = router.name if isinstance(router, Router) else router
        r = self._sub_routers.pop(name)
        r._parent = None
        return r

    async def propagate_event(self, event: Event, di: dict[str, Any]):
        for i in self._handler_managers.values():
            manager_di = copy(di)
            await i.propagate_event(event, manager_di)
            if event.propagation_stopped:
                return

        for r in self._sub_routers.values():
            subrouter_di = copy(di)
            await r.propagate_event(event, subrouter_di)
            if event.propagation_stopped:
                return

    @property
    def name(self) -> str:
        return self._name

    @property
    def parent(self) -> Router | None:
        return self._parent