from __future__ import annotations


__all__ = ['Router']

from typing import TYPE_CHECKING, Any
from copy import copy
from collections.abc import Generator

from eventry._config import AsyncEventDispatchingConfig as EventDispatchingConfig
from eventry._execution_context import ExecutionContext, RouterExecutionContext


if TYPE_CHECKING:
    from eventry.event import Event
    from eventry.asyncio.handler_manager import HandlerManager


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
        router_execution_ctx = RouterExecutionContext(
            router=self, **execution_ctx.shallow_asdict()
        )
        for i in self._handler_managers.values():
            manager_context = copy(context)

            await i.propagate_event(event, config, router_execution_ctx, manager_context)
            if event.propagation_stopped:
                return

        for r in self._sub_routers.values():
            subrouter_context = copy(context)
            await r.propagate_event(event, config, execution_ctx, subrouter_context)
            if event.propagation_stopped:
                return

    def chain_to_root(self) -> Generator[Router, None, None]:
        r = self
        while r is not None:
            yield r
            r = r.parent

    def chain_to_tails(self) -> Generator[Router, None, None]:
        yield self
        for r in self._sub_routers.values():
            yield from r.chain_to_tails()

    @property
    def name(self) -> str:
        return self._name

    @property
    def full_name(self) -> str:
        return '.'.join(f'{r.name!r}' for r in self.chain_to_root())

    @property
    def parent(self) -> Router | None:
        return self._parent
