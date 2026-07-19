from __future__ import annotations


__all__ = [
    'HandlerManager',
    'HandlerManagerConfig',
]

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar
from types import MappingProxyType
from functools import partial
from collections.abc import Callable, Sequence, Awaitable, Generator

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
from eventry.asyncio.callable_wrappers import Handler, CallableWrapper
from eventry.asyncio.middleware_manager import (
    MiddlewareManager,
    MiddlewareRegistrar,
    MiddlewareManagerType,
)


if TYPE_CHECKING:
    from eventry.event import Event

    EventFilterCallable = Callable[[Event], bool]
    EventFilter = EventFilterCallable | str


T = TypeVar('T')


MgrMdwsType = Literal[
    MiddlewareManagerType.MANAGER_OUTER,
    MiddlewareManagerType.MANAGER_INNER,
    MiddlewareManagerType.HANDLER_OUTER,
    MiddlewareManagerType.HANDLER_INNER,
    'manager.outer',
    'manager.inner',
    'handler.outer',
    'handler.inner',
]

ManagerMdwTypes = [
    MiddlewareManagerType.MANAGER_OUTER,
    MiddlewareManagerType.MANAGER_INNER,
    MiddlewareManagerType.HANDLER_OUTER,
    MiddlewareManagerType.HANDLER_INNER,
]


ManagerOuterMdwT = TypeVar('ManagerOuterMdwT')
ManagerFilterT = TypeVar('ManagerFilterT')
ManagerInnerMdwT = TypeVar('ManagerInnerMdwT')
HandlerOuterMdwT = TypeVar('HandlerOuterMdwT')
HandlerFilterT = TypeVar('HandlerFilterT')
HandlerInnerMdwT = TypeVar('HandlerInnerMdwT')
HandlerT = TypeVar('HandlerT')


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
        self._middleware_managers: dict[MiddlewareManagerType, MiddlewareManager] = {}
        self._filter: Filter = dummy_filter()

        self.middleware: MiddlewareRegistrar[MgrMdwsType] = MiddlewareRegistrar(
            self,
            ManagerMdwTypes,
        )

    def set_filter(self, filter: ManagerFilterT) -> None:
        self._filter = filter if isinstance(filter, Filter) else FilterFromFunction(filter)

    def remove_filter(self) -> None:
        self._filter = dummy_filter()

    def get_middleware_manager(self, manager_type: MgrMdwsType) -> MiddlewareManager | None:
        try:
            mdw_type = MiddlewareManagerType(manager_type)
        except ValueError:
            return None
        return self._middleware_managers.get(mdw_type)

    def set_middleware_manager(
        self, manager_type: MgrMdwsType, manager: MiddlewareManager | None
    ) -> None:
        if manager is not None and not isinstance(manager, MiddlewareManager):
            raise TypeError(
                f'Middleware manager must be an instance of MiddlewareManager, '
                f'not {type(manager)!r}.',
            )

        try:
            manager_type = MiddlewareManagerType(manager_type)
        except ValueError:
            raise ValueError(f'Invalid middleware manager type: {manager_type!r}.') from None

        if manager_type not in ManagerMdwTypes:
            raise ValueError(
                f'Handler manager does not support {manager_type!r} type of middleware manager.',
            )

        if manager is not None:
            self._middleware_managers[manager_type] = manager
        else:
            self._middleware_managers.pop(manager_type, None)

    def check_event(self, event: Event) -> bool:
        if self.event_filter is None:
            return True
        if isinstance(self.event_filter, str):
            return self.event_filter == event.name

        return self.event_filter(event)

    def _create_handler_obj(
        self,
        handler: Any,  # todo
        event_filter: EventFilter | None = None,
        handler_id: str | None = None,
        filter: Any = None,
        as_task: bool = False,
        inner_middlewares: Sequence[Any] | None = None,
        outer_middlewares: Sequence[Any] | None = None,
    ) -> Handler[Any]:
        if not handler_id:
            handler_id = gen_default_handler_id(handler)
            while handler_id in self._handlers:
                handler_id += '_'

        return Handler(
            handler,
            handler_id=handler_id,
            event_filter=event_filter,
            filter=convert_filters([filter])[0] if filter is not None else None,
            as_task=as_task,
            inner_middlewares=inner_middlewares,
            outer_middlewares=outer_middlewares,
        )

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

    def get_matching_handlers(self, event: Event) -> Generator[Handler[Any], None]:
        """
        Iterates through all registered handlers and yields those whose filters
        match the given event.

        :param event: The incoming event to check against handler filters.

        :return: An async generator yielding handlers that should handle the event.
        """
        for handler in self._handlers.values():
            if self.event_filter is not None:
                yield handler
            else:
                if handler.check_event(event):
                    yield handler

    def __call__(
        self,
        filter: HandlerFilterT | None = None,
        /,
        *,
        event_filter: EventFilter | None = None,
        handler_id: str | None = None,
        as_task: bool = False,
        inner_middlewares: Sequence[HandlerInnerMdwT] | None = None,
        outer_middlewares: Sequence[HandlerOuterMdwT] | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        def inner(handler: HandlerT) -> HandlerT:
            handler_obj = self._create_handler_obj(
                handler=handler,
                event_filter=event_filter,
                handler_id=handler_id,
                filter=filter,
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
        return await MiddlewareManager.wrap_with_middlewares(
            partial(handler, self.config.collect_handler_args(context)),
            list(self.get_middleware_manager('handler.inner') or []) + handler.inner_middlewares,
            make_mdw_wrapper_factory(self.config.collect_handler_inner_mdw_args),
        )(context)

    async def _execute_handler_with_filter_inner(
        self, handler: Handler[Any], context: dict[str, Any],
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
        h_execution_ctx = HandlerExecutionContext(
            handler=handler, **execution_ctx.shallow_asdict(),
        )
        try:
            handler_result = await MiddlewareManager.wrap_with_middlewares(
                partial(self._execute_handler_with_filter_inner, handler),
                list(self.get_middleware_manager('handler.outer') or []) + handler.outer_middlewares,
                make_mdw_wrapper_factory(self.config.collect_handler_outer_mdw_args),
            )(context)
        except Exception as handler_error:
            try:
                await config.on_error(h_execution_ctx, handler_error)
            except Exception as callback_error:
                if callback_error is handler_error:
                    raise callback_error
                logger.error(
                    f'An error occurred while executing error callback of handler '
                    f'{handler.id!r} @ {h_execution_ctx.manager.name!r} @ '
                    f'{h_execution_ctx.router.full_name} '
                    f'for event {h_execution_ctx.event.name!r}.',
                    exc_info=handler_error,
                )
            return

        try:
            await config.on_handler(h_execution_ctx, handler_result)
        except Exception as e:
            logger.error(
                f'An error occurred while executing callback of handler '
                f'{handler.id!r} @ {h_execution_ctx.manager.name!r} @ '
                f'{h_execution_ctx.router.full_name} '
                f'for event {h_execution_ctx.event.name!r}.',
                exc_info=e,
            )

    async def _execute_handlers_inner(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: ManagerExecutionContext,
        context: dict[str, Any],
    ):
        for i in self.get_matching_handlers(event):
            handler_context = context | {'handler': i}
            if i.as_task:
                asyncio.create_task(
                    self._execute_handler_with_filter(i, config, execution_ctx, handler_context),
                )
            else:
                await self._execute_handler_with_filter(i, config, execution_ctx, handler_context)
            if event.propagation_stopped:
                return

    async def _execute_handlers(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: ManagerExecutionContext,
        context: dict[str, Any],
    ):
        return await MiddlewareManager.wrap_with_middlewares(
            partial(self._execute_handlers_inner, event, config, execution_ctx),
            self.get_middleware_manager('manager.inner') or [],
            make_mdw_wrapper_factory(self.config.collect_manager_inner_mdw_args),
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
            return await MiddlewareManager.wrap_with_middlewares(
                partial(self._execute_handlers_with_mgr_filter, event, config, manager_ctx),
                self.get_middleware_manager('manager.outer') or [],
                make_mdw_wrapper_factory(self.config.collect_manager_outer_mdw_args),
            )(context)
        except Exception as manager_error:
            try:
                await config.on_error(manager_ctx, manager_error)
            except Exception as callback_error:
                if callback_error is manager_error:
                    raise callback_error
                logger.error('Error in manager callback', exc_info=callback_error)  # todo


def gen_default_handler_id(handler: Any):
    if inspect.isfunction(handler) or inspect.ismethod(handler) or inspect.isclass(handler):
        return f'{handler.__qualname__}'
    return f'{handler.__class__.__qualname__}'


_CALLABLE = Callable[[dict[str, Any]], Awaitable[Any]]


def make_mdw_wrapper_factory(
    args_call: Callable[[dict[str, Any]], list[Any]] | None = None,
    next_call_arg_name: str = 'next_call',
) -> Callable[[_CALLABLE, _CALLABLE | None], _CALLABLE]:
    def wrapper_factory(to_wrap: _CALLABLE, prev_wrapped: _CALLABLE | None) -> _CALLABLE:
        async def wrapped(context: dict[str, Any]) -> Any:
            if prev_wrapped is None:
                return await to_wrap(context)

            context.update({next_call_arg_name: prev_wrapped})
            call = to_wrap if isinstance(to_wrap, CallableWrapper) else CallableWrapper(to_wrap)
            return await call(args_call(context) if args_call is not None else [], context)

        return wrapped

    return wrapper_factory
