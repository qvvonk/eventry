from __future__ import annotations


__all__ = [
    'Router',
    'RouterConfig',
]

import asyncio
from typing import Any, Generic, TypeVar
from types import MappingProxyType
from functools import partial
from collections.abc import Mapping, Generator

from eventry.loggers import logger
from eventry.asyncio.config import RouterConfig, EventDispatchingConfig
from eventry.asyncio.filter import Filter, FilterFromFunction, dummy_filter
from eventry.asyncio.exceptions import router as rexc
from eventry.asyncio.middleware import (
    MiddlewareManager,
    MiddlewareStorage,
    _make_mdw_wrapper_factory,
)
from eventry.asyncio.dispatching_context import DispatchingContext
from eventry.asyncio.handler_manager.base import HandlerManager, HandlerManagerDefaultType


ManagerT = TypeVar('ManagerT', bound=HandlerManagerDefaultType)
FilterT = TypeVar('FilterT', bound=Any | Filter)
R = TypeVar('R', bound='Router[Any]')


class Router(Generic[FilterT]):
    def __init__(self, name: str = '', config: RouterConfig | None = None) -> None:
        if not isinstance(name, str):
            raise TypeError(f'Router name must be a string, not {type(config)!r}.')

        if config is not None and not isinstance(config, RouterConfig):
            raise TypeError(f'Config must be an instance of `RouterConfig`, not {type(config)!r}.')

        self._name = name or self.__class__.__name__
        self._sub_routers: dict[str, Router[Any]] = {}
        self._sub_routers_proxy = MappingProxyType(self._sub_routers)
        self._handler_managers: dict[str, HandlerManagerDefaultType] = {}
        self._handler_managers_proxy = MappingProxyType(self._handler_managers)
        self._parent: Router[Any] | None = None
        self._config = config if config is not None else RouterConfig()
        self._filter: Filter = dummy_filter()
        self.middleware = MiddlewareManager(['router.outer', 'router.inner'])

    def set_filter(self, filter: FilterT) -> None:
        self._filter = filter if isinstance(filter, Filter) else FilterFromFunction(filter)

    def remove_filter(self) -> None:
        self._filter = dummy_filter()

    def attach_router(self, router: Router[Any]) -> None:
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

    def detach_router(self, router_name: str) -> Router[Any]:
        if not isinstance(router_name, str):
            raise TypeError('Router name must be a string.')

        if router_name not in self._sub_routers:
            raise KeyError(
                f'Router {self.full_name} does not has a subrouter with name {router_name!r}.',
            )

        r = self._sub_routers.pop(router_name)
        r._parent = None
        return r

    def detach(self: R) -> R:
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

    def remove_handler_manager(self, name: str) -> HandlerManagerDefaultType | None:
        return self._handler_managers.pop(name, None)

    async def _propagate_event(self, cfg: EventDispatchingConfig, ctx: DispatchingContext) -> None:
        for i in self._handler_managers.values():
            manager_ctx = ctx.fork(manager=i)
            (await i.propagate_event(cfg, manager_ctx),)
            if manager_ctx.event.propagation_stopped:
                return

        for r in self._sub_routers.values():
            subrouter_ctx = ctx.fork(router=r)
            await r.propagate_event(cfg, subrouter_ctx)
            if subrouter_ctx.event.propagation_stopped:
                return

    async def _propagate_event_with_filter(
        self,
        cfg: EventDispatchingConfig,
        ctx: DispatchingContext,
    ) -> Any:
        r = await self.filter.execute(ctx.args.router.filter, ctx)
        if not r and not isinstance(r, dict):
            return None

        return await MiddlewareStorage.wrap_with_middlewares(
            partial(self._propagate_event, cfg),
            self.middleware.get_middlewares_storage('router.inner') or [],
            _make_mdw_wrapper_factory(ctx.args.router.inner, self.config.inner_mdw_next_call_key),
        )(ctx)

    async def propagate_event(self, cfg: EventDispatchingConfig, ctx: DispatchingContext) -> Any:
        ctx.args.router.outer = list(self.config.outer_mdw_args)
        ctx.args.router.filter = list(self.config.filter_args)
        ctx.args.router.inner = list(self.config.inner_mdw_args)

        try:
            return await MiddlewareStorage.wrap_with_middlewares(
                partial(self._propagate_event_with_filter, cfg),
                self.middleware.get_middlewares_storage('router.outer') or [],
                _make_mdw_wrapper_factory(
                    ctx.args.router.outer, self.config.outer_mdw_next_call_key
                ),
            )(ctx)
        except Exception as router_error:
            try:
                await cfg.on_error(ctx, router_error)
            except Exception as callback_error:
                if callback_error is router_error:
                    raise callback_error
                logger.error('Error in router callback', exc_info=callback_error)  # todo

    def chain_to_root(self) -> Generator[Router[Any], None, None]:
        r: Router[Any] | None = self
        while r is not None:
            yield r
            r = r.parent

    def chain_to_tails(self) -> Generator[Router[Any], None, None]:
        yield self
        for r in self._sub_routers.values():
            yield from r.chain_to_tails()

    def handler_tasks(self) -> Generator[asyncio.Task[Any], None, None]:
        for mgr in self.handler_managers.values():
            for task in mgr.handler_tasks:
                yield task

        for router in self.sub_routers.values():
            yield from router.handler_tasks()

    def __repr__(self) -> str:
        return f'Router({self.name!r})'

    @property
    def name(self) -> str:
        return self._name

    @property
    def full_name(self) -> str:
        return '.'.join(f'{r.name!r}' for r in reversed(list(self.chain_to_root())))

    @property
    def path(self) -> tuple[str, ...]:
        return tuple(reversed([i.name for i in self.chain_to_root()]))

    @property
    def parent(self) -> Router[Any] | None:
        return self._parent

    @property
    def config(self) -> RouterConfig:
        return self._config

    @property
    def filter(self) -> Filter:
        return self._filter

    @property
    def handler_managers(self) -> Mapping[str, HandlerManagerDefaultType]:
        return self._handler_managers_proxy

    @property
    def sub_routers(self) -> Mapping[str, Router[Any]]:
        return self._sub_routers_proxy
