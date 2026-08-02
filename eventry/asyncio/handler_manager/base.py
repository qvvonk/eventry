from __future__ import annotations


__all__ = [
    'HandlerManager',
    'HandlerManagerConfig',
    'HandlerManagerDefaultType',
    'HandlerManagerAnyType',
]

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Generic, TypeVar
from types import MappingProxyType
from functools import partial
from collections.abc import Callable, Sequence

from eventry.loggers import logger
from eventry.asyncio.config import DispatchingConfig, HandlerManagerConfig
from eventry.asyncio.filter import Filter, FilterFromFunction, dummy_filter, convert_filters
from eventry.asyncio.middleware import (
    MiddlewareManager,
    MiddlewareStorage,
    _make_mdw_wrapper_factory,
)
from eventry.asyncio.callable_wrappers import Handler
from eventry.asyncio.dispatching_context import DispatchingContext


if TYPE_CHECKING:
    from eventry._event import Event

    EventFilterCallable = Callable[[Event], bool]
    EventFilter = EventFilterCallable | str


# ManagerOuterMdwT = TypeVar('ManagerOuterMdwT', bound=Callable[..., Any])
ManagerFilterT = TypeVar('ManagerFilterT', bound=Callable[..., Any])
# ManagerInnerMdwT = TypeVar('ManagerInnerMdwT', bound=Callable[..., Any])
HandlerOuterMdwT = TypeVar('HandlerOuterMdwT', bound=Callable[..., Any])
HandlerFilterT = TypeVar('HandlerFilterT', bound=Callable[..., Any])
HandlerInnerMdwT = TypeVar('HandlerInnerMdwT', bound=Callable[..., Any])
HandlerT = TypeVar('HandlerT', bound=Callable[..., Any])


class HandlerManager(
    Generic[
        # ManagerOuterMdwT,
        ManagerFilterT,
        # ManagerInnerMdwT,
        HandlerOuterMdwT,
        HandlerFilterT,
        HandlerInnerMdwT,
        HandlerT,
    ],
):
    def __init__(
        self,
        name: str,
        event_filter: EventFilter | None = None,
        config: HandlerManagerConfig | None = None,
    ) -> None:
        """
        :param name: handler manager name.
        :param event_filter: event name filter.
        :param config: `HandlerManagerConfig` instance.
        """
        self._handlers: dict[str, Handler[Any]] = {}
        self._event_filter = event_filter
        self._name = name
        self._config = config or HandlerManagerConfig()
        self._filter: Filter = dummy_filter()
        self.middleware = MiddlewareManager(
            ['manager.outer', 'manager.inner', 'handler.outer', 'handler.inner'],
        )
        self._handler_tasks: set[asyncio.Task[Any]] = set()

    @property
    def handlers(self) -> MappingProxyType[str, Handler[Any]]:
        """
        A read-only mapping of handler IDs to their corresponding ``Handler`` instances,
        registered in this manager.
        """
        return MappingProxyType(self._handlers)

    @property
    def name(self) -> str:
        return self._name

    @property
    def event_filter(self) -> EventFilter | None:
        return self._event_filter

    @property
    def config(self) -> HandlerManagerConfig:
        return self._config

    @property
    def filter(self) -> Filter:
        return self._filter

    @property
    def handler_tasks(self) -> set[asyncio.Task[Any]]:
        return self._handler_tasks

    def set_filter(self, filter: ManagerFilterT) -> None:
        self._filter = filter if isinstance(filter, Filter) else FilterFromFunction(filter)

    def remove_filter(self) -> None:
        self._filter = dummy_filter()

    def check_event(self, event: Event) -> bool:
        if self.event_filter is None:
            return True

        if isinstance(self.event_filter, str):
            return self.event_filter == event.name

        return self.event_filter(event)

    def _register_handler(self, handler: Handler[Any]) -> None:
        """
        Registers handler to this handler manager.

        Before registration, traverses the entire router network (starting from the root router)
        to check for duplicate handler IDs. If a handler with the same ID is found anywhere
        in the network, raises a ``ValueError``.

        :param handler: ``Handler`` instance to register.

        :raises ValueError: if a handler with the same ID already exists in the router network.
        """
        if handler.name in self._handlers:
            raise ValueError(f'Handler with ID {handler.name} already exists in this manager.')
        self._handlers[handler.name] = handler

    def __call__(
        self,
        filter: HandlerFilterT | None = None,
        /,
        *,
        name: str | None = None,
        as_task: bool = False,
        inner_middlewares: Sequence[HandlerInnerMdwT] | None = None,
        outer_middlewares: Sequence[HandlerOuterMdwT] | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        def inner(handler: HandlerT) -> HandlerT:
            handler_obj = Handler(
                handler,
                name=name or gen_handler_name(handler, list(self._handlers.keys())),
                filter=convert_filters([filter])[0] if filter is not None else None,
                as_task=as_task,
                outer_middlewares=outer_middlewares,
                inner_middlewares=inner_middlewares,
            )
            self._register_handler(handler_obj)
            return handler

        return inner

    async def _handler(self, handler: Handler[Any], ctx: DispatchingContext) -> Any:
        return await handler(ctx.args.handler.call, ctx)

    async def _execute_handler(self, handler: Handler[Any], ctx: DispatchingContext) -> Any:
        return await MiddlewareStorage.wrap_with_middlewares(
            partial(self._handler, handler),
            list(self.middleware.get_middlewares_storage('handler.inner') or [])
            + handler.inner_middlewares,
            _make_mdw_wrapper_factory(
                ctx.args.handler.inner, self.config.handler_inner_mdw_next_call_key
            ),
        )(ctx)

    async def _execute_handler_with_filter_inner(
        self,
        handler: Handler[Any],
        ctx: DispatchingContext,
    ) -> Any:
        r = await handler.filter.execute(ctx.args.handler.filter, ctx)
        if not r and not isinstance(r, dict):
            return r

        return await self._execute_handler(handler, ctx)

    async def _execute_handler_with_filter(
        self, handler: Handler[Any], ctx: DispatchingContext
    ) -> Any:
        return await MiddlewareStorage.wrap_with_middlewares(
            partial(self._execute_handler_with_filter_inner, handler),
            list(self.middleware.get_middlewares_storage('handler.outer') or [])
            + handler.outer_middlewares,
            _make_mdw_wrapper_factory(
                ctx.args.handler.outer,
                self.config.handler_outer_mdw_next_call_key,
            ),
        )(ctx)

    async def _handler_callback(
        self,
        handler: Handler[Any],
        cfg: DispatchingConfig,
        ctx: DispatchingContext,
        task: asyncio.Task[Any] | None = None,
        exception: Exception | None = None,
        result: Any = None,
    ) -> None:
        if task is not None:
            self._handler_tasks.discard(task)

            try:
                result = task.result()
            except Exception as e:
                exception = e

        if exception is None:
            try:
                await cfg.on_handler(ctx, result)
            except Exception as e:
                logger.error(
                    f'An error occurred while executing callback of handler '
                    f'{handler.name!r} @ {self.name!r} @ {ctx.router.full_name} '
                    f'for event {ctx.event.name!r}.',
                    exc_info=e,
                )
            return

        try:
            await cfg.on_error(ctx, exception)
        except Exception as e:
            if e is exception and task is None:
                raise

            logger.error(
                f'An error occurred while executing error callback of handler '
                f'{handler.name!r} @ {self.name!r} @ {ctx.router.full_name} '
                f'for event {ctx.event.name!r}.',
                exc_info=e,
            )

    async def _execute_handlers_inner(
        self, cfg: DispatchingConfig, ctx: DispatchingContext
    ) -> Any:
        for handler in self.handlers.values():
            handler_ctx = ctx.fork(handler=handler)
            coro = self._execute_handler_with_filter(handler, handler_ctx)

            if handler.as_task:
                task = asyncio.create_task(coro)
                cb = partial(self._handler_callback, handler=handler, cfg=cfg, ctx=handler_ctx)
                task.add_done_callback(
                    lambda t, c=cb: asyncio.create_task(c(task=t)) # type: ignore[misc]
                )

                self._handler_tasks.add(task)

            else:
                exception, result = None, None
                try:
                    result = await coro
                except Exception as e:
                    exception = e
                await self._handler_callback(
                    handler=handler, ctx=handler_ctx, cfg=cfg, exception=exception, result=result
                )

            if handler_ctx.event.propagation_stopped:
                return

    async def _execute_handlers(self, cfg: DispatchingConfig, ctx: DispatchingContext) -> Any:
        return await MiddlewareStorage.wrap_with_middlewares(
            partial(self._execute_handlers_inner, cfg),
            self.middleware.get_middlewares_storage('manager.inner') or [],
            _make_mdw_wrapper_factory(
                ctx.args.manager.inner,
                self.config.manager_inner_mdw_next_call_key,
            ),
        )(ctx)

    async def _execute_handlers_with_mgr_filter(
        self, cfg: DispatchingConfig, ctx: DispatchingContext
    ) -> Any:
        r = await self.filter.execute(ctx.args.manager.filter, ctx)
        if r is False or r is None:
            return r

        return await self._execute_handlers(cfg, ctx)

    async def propagate_event(self, cfg: DispatchingConfig, ctx: DispatchingContext) -> Any:
        if not self.check_event(ctx.event):
            return None

        ctx.args.manager.outer = list(self.config.manager_outer_mdw_args)
        ctx.args.manager.filter = list(self.config.manager_filter_args)
        ctx.args.manager.inner = list(self.config.manager_inner_mdw_args)
        ctx.args.handler.outer = list(self.config.handler_outer_mdw_args)
        ctx.args.handler.filter = list(self.config.handler_filter_args)
        ctx.args.handler.inner = list(self.config.handler_inner_mdw_args)
        ctx.args.handler.call = list(self.config.handler_args)

        try:
            return await MiddlewareStorage.wrap_with_middlewares(
                partial(self._execute_handlers_with_mgr_filter, cfg),
                self.middleware.get_middlewares_storage('manager.outer') or [],
                _make_mdw_wrapper_factory(
                    ctx.args.manager.outer,
                    self.config.manager_outer_mdw_next_call_key,
                ),
            )(ctx)
        except Exception as manager_error:
            try:
                await cfg.on_error(ctx, manager_error)
            except Exception as callback_error:
                if callback_error is manager_error:
                    raise callback_error
                logger.error('Error in manager callback', exc_info=callback_error)  # todo


HandlerManagerDefaultType = HandlerManager[
    # Callable[..., Any],
    Callable[..., Any],
    # Callable[..., Any],
    Callable[..., Any],
    Callable[..., Any],
    Callable[..., Any],
    Callable[..., Any],
]

HandlerManagerAnyType = HandlerManager[Any, Any, Any, Any, Any]


def gen_handler_name(handler: Any, names: Sequence[str] = ()) -> str:
    r = handler.__qualname__ if inspect.isroutine(handler) else handler.__class__.__name__
    if r not in names:
        return r

    index = 1
    while f'{r}_{index}' in names:
        index += 1
    return f'{r}_{index}'
