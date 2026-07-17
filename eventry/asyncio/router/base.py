from __future__ import annotations


__all__ = ['Router']


from typing import TYPE_CHECKING, Any
from collections.abc import Generator
from copy import copy
from eventry._execution_context import ExecutionContext, RouterExecutionContext
from eventry._config import AsyncEventDispatchingConfig as EventDispatchingConfig

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

    async def propagate_event(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: ExecutionContext,
        context: dict[str, Any],
    ):
        for i in self._handler_managers.values():
            manager_context = copy(context)
            await i.propagate_event(event, manager_context)
            if event.propagation_stopped:
                return

        for r in self._sub_routers.values():
            subrouter_context = copy(context)
            await r.propagate_event(event, config, execution_ctx, subrouter_context)
            if event.propagation_stopped:
                return

    @property
    def chain_to_root(self) -> Generator[Router, None, None]:
        r = self
        while r.parent is not None:
            yield r
            r = r.parent

    @property
    def chain_to_tails(self) -> Generator[Router, None, None]:
        yield self
        for r in self._sub_routers.values():
            yield from r.chain_to_tails

    @property
    def name(self) -> str:
        return self._name

    @property
    def parent(self) -> Router | None:
        return self._parent