from __future__ import annotations


__all__ = ['Router', 'RouterConfig']

from typing import TYPE_CHECKING, Any, Self, Generic, TypeVar
from copy import copy
from types import MappingProxyType
from functools import partial
from collections.abc import Mapping, Generator

from eventry._config import RouterConfig, AsyncEventDispatchingConfig as EventDispatchingConfig
from eventry.asyncio.filter import Filter, FilterFromFunction, dummy_filter
from eventry._execution_context import ExecutionContext, RouterExecutionContext
from eventry.asyncio.exceptions import router as rexc
from eventry.asyncio.middleware_manager import (
    MiddlewareManager,
    MiddlewareStorage,
    _make_mdw_wrapper_factory,
)
from eventry.asyncio.handler_manager.base import HandlerManager


if TYPE_CHECKING:
    from eventry.event import Event

    ManagerT = TypeVar('ManagerT', bound=HandlerManager)


FilterT = TypeVar('FilterT')


class Router(Generic[FilterT]):
    def __init__(self, name: str = '', config: RouterConfig | None = None) -> None:
        if not isinstance(name, str):
            raise TypeError(f'Router name must be a string, not {type(config)!r}.')

        if config is not None and not isinstance(config, RouterConfig):
            raise TypeError(f'Config must be an instance of `RouterConfig`, not {type(config)!r}.')

        self._name = name or self.__class__.__name__
        self._sub_routers: dict[str, Router] = {}
        self._sub_routers_proxy = MappingProxyType(self._sub_routers)
        self._handler_managers: dict[str, HandlerManager] = {}
        self._handler_managers_proxy = MappingProxyType(self._handler_managers)
        self._parent: Router | None = None
        self._config = config if config is not None else RouterConfig()
        self._filter: Filter = dummy_filter()
        self.middleware = MiddlewareManager(['router.outer', 'router.inner'])

    def set_filter(self, filter: FilterT) -> None:
        self._filter = filter if isinstance(filter, Filter) else FilterFromFunction(filter)

    def remove_filter(self) -> None:
        self._filter = dummy_filter()

    def attach_router(self, router: Router) -> None:
        if router is self:
            raise rexc.RouterLoopError('Cannot attach router to itself.')

        if router.parent is not None:
            raise rexc.RouterAlreadyAttachedError(
                f'Router {router.full_name!r} already has a parent.',
            )

        if router.name in self._sub_routers:
            raise rexc.DuplicateSubrouterNameError(
                f'Router {self.full_name} already has a subrouter with name {router.name!r}.',
            )

        for i in self.chain_to_root():
            if i is router:
                raise rexc.RouterLoopError('Cannot attach an ancestor router.')

        self._sub_routers[router.name] = router
        router._parent = self

    def detach_router(self, router_name: str) -> Router:
        if not isinstance(router_name, str):
            raise TypeError('Router name must be a string.')

        if router_name not in self._sub_routers:
            raise KeyError(
                f'Router {self.full_name} does not has a subrouter with name {router_name!r}.',
            )

        r = self._sub_routers.pop(router_name)
        r._parent = None
        return r

    def detach(self) -> Self:
        if self.parent is not None:
            self.parent.detach_router(self.name)
        return self

    def add_handler_manager(self, manager: ManagerT) -> ManagerT:
        if not isinstance(manager, HandlerManager):
            raise TypeError(
                f'Handler manager must be an instance of `HandlerManager`, not {type(manager)!r}',
            )

        if manager.name in self._handler_managers:
            raise ValueError(
                f'Handler manager with name {manager.name!r} already exists in this router.',
            )

        self._handler_managers[manager.name] = manager
        return manager

    def remove_handler_manager(self, name: str) -> HandlerManager | None:
        return self._handler_managers.pop(name)

    async def _propagate_event(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: RouterExecutionContext,
        context: dict[str, Any],
    ):
        for i in self._handler_managers.values():
            manager_context = context | {i.config.manager_key: i}

            await i.propagate_event(event, config, execution_ctx, manager_context)
            if event.propagation_stopped:
                return

        for r in self._sub_routers.values():
            subrouter_context = copy(context)
            await r._propagate_event(event, config, execution_ctx, subrouter_context)
            if event.propagation_stopped:
                return

    async def _propagate_event_with_filter_inner(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: RouterExecutionContext,
        context: dict[str, Any],
    ):
        r = await self.filter.execute(self.config.collect_filter_args(context), context)
        if not r and not isinstance(r, dict):
            return r

        return await self._propagate_event(event, config, execution_ctx, context)

    async def _propagate_event_with_filter(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: RouterExecutionContext,
        context: dict[str, Any],
    ):
        return await MiddlewareStorage.wrap_with_middlewares(
            partial(self._propagate_event_with_filter_inner, event, config, execution_ctx),
            self.middleware.get_middlewares_storage('router.inner') or [],
            _make_mdw_wrapper_factory(self.config.collect_inner_mdw_args),
        )(context)

    async def propagate_event(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: ExecutionContext,
        context: dict[str, Any],
    ):
        execution_ctx = RouterExecutionContext(
            **(execution_ctx.shallow_asdict() | {'router': self}),
        )
        context[self.config.router_key] = self

        self.config.update_ctx_with_outer_mdw_args(context)
        self.config.update_ctx_with_filter_args(context)
        self.config.update_ctx_with_inner_mdw_args(context)

        return await MiddlewareStorage.wrap_with_middlewares(
            partial(self._propagate_event_with_filter, event, config, execution_ctx),
            self.middleware.get_middlewares_storage('router.outer') or [],
            _make_mdw_wrapper_factory(self.config.collect_outer_mdw_args),
        )(context)

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
    def path(self) -> tuple[str, ...]:
        return tuple(reversed([i.name for i in self.chain_to_root()]))

    @property
    def parent(self) -> Router | None:
        return self._parent

    @property
    def config(self) -> RouterConfig:
        return self._config

    @property
    def filter(self) -> Filter:
        return self._filter

    @property
    def handler_managers(self) -> Mapping[str, HandlerManager]:
        return self._handler_managers_proxy

    @property
    def sub_routers(self) -> Mapping[str, Router]:
        return self._sub_routers_proxy
