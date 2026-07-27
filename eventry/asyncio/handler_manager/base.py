from __future__ import annotations


__all__ = [
    'HandlerManager',
    'HandlerManagerConfig',
]

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Generic, TypeVar
from types import MappingProxyType
from functools import partial
from collections.abc import Callable, Sequence

from eventry._config import (
    HandlerManagerConfig,
    AsyncEventDispatchingConfig as EventDispatchingConfig,
)
from eventry.loggers import logger
from eventry.asyncio.filter import Filter, FilterFromFunction, dummy_filter, convert_filters
from eventry._execution_context import (
    RouterExecutionContext,
    HandlerExecutionContext,
    ManagerExecutionContext,
)
from eventry.asyncio.callable_wrappers import Handler
from eventry.asyncio.middleware_manager import (
    MiddlewareManager,
    MiddlewareStorage,
    _make_mdw_wrapper_factory,
)


if TYPE_CHECKING:
    from eventry.event import Event

    EventFilterCallable = Callable[[Event], bool]
    EventFilter = EventFilterCallable | str


T = TypeVar('T')


ManagerOuterMdwT = TypeVar('ManagerOuterMdwT', default=Callable[..., Any])
ManagerFilterT = TypeVar('ManagerFilterT', default=Callable[..., Any])
ManagerInnerMdwT = TypeVar('ManagerInnerMdwT', default=Callable[..., Any])
HandlerOuterMdwT = TypeVar('HandlerOuterMdwT', default=Callable[..., Any])
HandlerFilterT = TypeVar('HandlerFilterT', default=Callable[..., Any])
HandlerInnerMdwT = TypeVar('HandlerInnerMdwT', default=Callable[..., Any])
HandlerT = TypeVar('HandlerT', default=Callable[..., Any])


class HandlerManager(
    Generic[
        ManagerOuterMdwT,
        ManagerFilterT,
        ManagerInnerMdwT,
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
        if handler.id in self._handlers:
            raise ValueError(f'Handler with ID {handler.id} already exists in this manager.')
        self._handlers[handler.id] = handler

    def __call__(
        self,
        filter: HandlerFilterT | None = None,
        /,
        *,
        handler_id: str | None = None,
        as_task: bool = False,
        inner_middlewares: Sequence[HandlerInnerMdwT] | None = None,
        outer_middlewares: Sequence[HandlerOuterMdwT] | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        def inner(handler: HandlerT) -> HandlerT:
            handler_obj = Handler(
                handler,
                handler_id=handler_id or gen_handler_id(handler, list(self._handlers.keys())),
                filter=convert_filters([filter])[0] if filter is not None else None,
                as_task=as_task,
                inner_middlewares=inner_middlewares,
                outer_middlewares=outer_middlewares,
            )
            self._register_handler(handler_obj)
            return handler

        return inner

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

    async def _execute_handler(self, handler: Handler[Any], context: dict[str, Any]) -> Any:
        return await MiddlewareStorage.wrap_with_middlewares(
            partial(handler, self.config.collect_handler_args(context)),
            list(self.middleware.get_middlewares_storage('handler.inner') or [])
            + handler.inner_middlewares,
            _make_mdw_wrapper_factory(
                self.config.collect_handler_inner_mdw_args,
                self.config.handler_inner_mdw_next_call_key,
            ),
        )(context)

    async def _execute_handler_with_filter_inner(
        self,
        handler: Handler[Any],
        context: dict[str, Any],
    ):
        r = await handler.filter.execute(self.config.collect_handler_filter_args(context), context)
        if not r and not isinstance(r, dict):
            return r

        return await self._execute_handler(handler, context)

    async def _execute_handler_with_filter(
        self,
        handler: Handler[Any],
        config: EventDispatchingConfig,
        execution_ctx: ManagerExecutionContext,
        context: dict[str, Any],
    ):
        h_exec_ctx = HandlerExecutionContext(handler=handler, **execution_ctx.shallow_asdict())
        try:
            handler_result = await MiddlewareStorage.wrap_with_middlewares(
                partial(self._execute_handler_with_filter_inner, handler),
                list(self.middleware.get_middlewares_storage('handler.outer') or [])
                + handler.outer_middlewares,
                _make_mdw_wrapper_factory(
                    self.config.collect_handler_outer_mdw_args,
                    self.config.handler_outer_mdw_next_call_key,
                ),
            )(context)
        except Exception as handler_error:
            try:
                await config.on_error(h_exec_ctx, handler_error)
            except Exception as callback_error:
                if callback_error is handler_error:
                    raise callback_error
                logger.error(
                    f'An error occurred while executing error callback of handler '
                    f'{handler.id!r} @ {h_exec_ctx.manager.name!r} @ '
                    f'{h_exec_ctx.router.full_name} '
                    f'for event {h_exec_ctx.event.name!r}.',
                    exc_info=handler_error,
                )
            return

        try:
            await config.on_handler(h_exec_ctx, handler_result)
        except Exception as e:
            logger.error(
                f'An error occurred while executing callback of handler '
                f'{handler.id!r} @ {h_exec_ctx.manager.name!r} @ '
                f'{h_exec_ctx.router.full_name} '
                f'for event {h_exec_ctx.event.name!r}.',
                exc_info=e,
            )

    async def _execute_handlers_inner(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: ManagerExecutionContext,
        context: dict[str, Any],
    ):
        for i in self.handlers.values():
            if i.as_task:
                asyncio.create_task(
                    self._execute_handler_with_filter(
                        i, config, execution_ctx, context | {self.config.handler_key: i},
                    ),
                )
            else:
                await self._execute_handler_with_filter(
                    i, config, execution_ctx, context | {self.config.handler_key: i},
                )
            if event.propagation_stopped:
                return

    async def _execute_handlers(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: ManagerExecutionContext,
        context: dict[str, Any],
    ):
        return await MiddlewareStorage.wrap_with_middlewares(
            partial(self._execute_handlers_inner, event, config, execution_ctx),
            self.middleware.get_middlewares_storage('manager.inner') or [],
            _make_mdw_wrapper_factory(
                self.config.collect_manager_inner_mdw_args,
                self.config.manager_inner_mdw_next_call_key,
            ),
        )(context)

    async def _execute_handlers_with_mgr_filter(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: ManagerExecutionContext,
        context: dict[str, Any],
    ):
        r = await self.filter.execute(self.config.collect_manager_filter_args(context), context)
        if r is False or r is None:
            return r

        return await self._execute_handlers(event, config, execution_ctx, context)

    async def propagate_event(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: RouterExecutionContext,
        context: dict[str, Any],
    ):
        if not self.check_event(event):
            return None

        self.config.update_ctx_with_manager_outer_mdw_args(context)
        self.config.update_ctx_with_manager_filter_args(context)
        self.config.update_ctx_with_manager_inner_mdw_args(context)
        self.config.update_ctx_with_handler_outer_mdw_args(context)
        self.config.update_ctx_with_handler_filter_args(context)
        self.config.update_ctx_with_handler_inner_mdw_args(context)
        self.config.update_ctx_with_handler_args(context)

        manager_ctx = ManagerExecutionContext(manager=self, **execution_ctx.shallow_asdict())
        try:
            return await MiddlewareStorage.wrap_with_middlewares(
                partial(self._execute_handlers_with_mgr_filter, event, config, manager_ctx),
                self.middleware.get_middlewares_storage('manager.outer') or [],
                _make_mdw_wrapper_factory(
                    self.config.collect_manager_outer_mdw_args,
                    self.config.manager_outer_mdw_next_call_key,
                ),
            )(context)
        except Exception as manager_error:
            try:
                await config.on_error(manager_ctx, manager_error)
            except Exception as callback_error:
                if callback_error is manager_error:
                    raise callback_error
                logger.error('Error in manager callback', exc_info=callback_error)  # todo


def gen_handler_id(handler: Any, names: Sequence[str] = ()) -> str:
    r = handler.__qualname__ if inspect.isroutine(handler) else handler.__clas__.__name__
    if r not in names:
        return r

    index = 1
    while f'{r}_{index}' in names:
        index += 1
    return f'{r}_{index}'
