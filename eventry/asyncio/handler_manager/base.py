from __future__ import annotations


__all__ = [
    'HandlerManager',
    'HandlerManagerConfig'
]

import inspect
from dataclasses import asdict
from functools import partial
from types import MappingProxyType
from collections.abc import Callable, Generator, Sequence, Awaitable
from copy import copy
from typing import TYPE_CHECKING, Any, TypeVar, Literal, Generic

from eventry.asyncio.filter import Filter, FilterFromFunction, convert_filters, dummy_filter
from eventry.asyncio.callable_wrappers import Handler, CallableWrapper
from eventry._config import HandlerManagerConfig
from eventry.asyncio.middleware_manager import MiddlewareManager, MiddlewareManagerType, MiddlewareRegistrar
from eventry._config import AsyncEventDispatchingConfig as EventDispatchingConfig
from eventry._execution_context import RouterExecutionContext, ManagerExecutionContext, HandlerExecutionContext
from eventry.loggers import logger


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
    'handler.inner'
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
    ]
):
    def __init__(self,
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
            self, ManagerMdwTypes
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

    def set_middleware_manager(self, manager_type: MgrMdwsType, manager: MiddlewareManager | None) -> None:
        if manager is not None and not isinstance(manager, MiddlewareManager):
            raise TypeError(
                f'Middleware manager must be an instance of MiddlewareManager, '
                f'not {type(manager)!r}.'
            )

        try:
            manager_type = MiddlewareManagerType(manager_type)
        except ValueError:
            raise ValueError(f'Invalid middleware manager type: {manager_type!r}.') from None

        if manager_type not in ManagerMdwTypes:
            raise ValueError(
                f'Handler manager does not support {manager_type!r} middleware manager.'
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

        handler_obj = Handler(
            handler,
            handler_id=handler_id,
            event_filter=event_filter,
            filter=convert_filters([filter])[0] if filter is not None else None,
            as_task=as_task,
            inner_middlewares=inner_middlewares,
            outer_middlewares=outer_middlewares,
        )
        return handler_obj

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

    async def _execute_handler_inner(self, handler: Handler[Any], context: dict[str, Any]):
        return await handler(self.config.collect_handler_args(context), context)

    async def _execute_handler(self, handler: Handler[Any], context: dict[str, Any]) -> Any:
        wrapped = MiddlewareManager.wrap_with_middlewares(
            partial(self._execute_handler_inner, handler),
            list(self.get_middleware_manager('handler.inner') or []) + handler.inner_middlewares,
            make_mdw_wrapper_factory(self.config.collect_handler_inner_mdw_args),
        )
        return await wrapped(context)

    async def _execute_handler_with_filter_inner(
        self,
        handler: Handler[Any],
        context: dict[str, Any]
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
        context: dict[str, Any]
    ):
        wrapped = MiddlewareManager.wrap_with_middlewares(
            partial(self._execute_handler_with_filter_inner, handler),
            list(self.get_middleware_manager('handler.outer') or []) + handler.outer_middlewares,
            make_mdw_wrapper_factory(self.config.collect_handler_outer_mdw_args)
        )

        try:
            return await wrapped(context)
        except Exception as handler_error:
            h_execution_ctx = HandlerExecutionContext(
                handler=handler,
                **asdict(execution_ctx) | {'exception': handler_error}
            )
            try:
                await config.on_error(h_execution_ctx)
            except Exception as callback_error:
                if callback_error is handler_error:
                    raise callback_error
                else:
                    logger.error(f'An error in handler callback', exc_info=callback_error)

    async def _execute_handlers_inner(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: ManagerExecutionContext,
        context: dict[str, Any],
    ):
        for i in self.get_matching_handlers(event):
            handler_context = copy(context) if self.config.isolate_handler_context else context
            await self._execute_handler_with_filter(i, config, execution_ctx, handler_context)
            if event.propagation_stopped:
                return

    async def _execute_handlers(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: ManagerExecutionContext,
        context: dict[str, Any]
    ):
        wrapped = MiddlewareManager.wrap_with_middlewares(
            partial(self._execute_handlers_inner, event, config, execution_ctx),
            self.get_middleware_manager('manager.inner') or [],
            make_mdw_wrapper_factory(self.config.collect_manager_inner_mdw_args)
        )
        return await wrapped(context)

    async def _execute_handlers_with_mgr_filter(
        self,
        event: Event,
        config: EventDispatchingConfig,
        execution_ctx: ManagerExecutionContext,
        context: dict[str, Any]
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
        context: dict[str, Any]
    ):
        self.config.update_di_with_manager_outer_mdw_args(context)
        self.config.update_di_with_manager_filter_args(context)
        self.config.update_di_with_manager_inner_mdw_args(context)
        self.config.update_di_with_handler_outer_mdw_args(context)
        self.config.update_di_with_handler_filter_args(context)
        self.config.update_di_with_handler_inner_mdw_args(context)
        self.config.update_di_with_handler_args(context)

        wrapped = MiddlewareManager.wrap_with_middlewares(
            partial(self._execute_handlers_with_mgr_filter, event, config, execution_ctx),
            self.get_middleware_manager('manager.outer') or [],
            make_mdw_wrapper_factory(self.config.collect_manager_outer_mdw_args)
        )

        manager_ctx = ManagerExecutionContext(manager=self, **asdict(execution_ctx))

        try:
            return await wrapped(context)
        except Exception as manager_error:
            try:
                error_ctx = ManagerExecutionContext(**asdict(manager_ctx) | {'exception': manager_error})
                await config.on_error(error_ctx)
            except Exception as callback_error:
                if callback_error is manager_error:
                    raise callback_error
                else:
                    logger.error('Error in manager callback', exc_info=callback_error) # todo



def gen_default_handler_id(handler: Any):
    if inspect.isfunction(handler) or inspect.ismethod(handler) or inspect.isclass(handler):
        return f'{handler.__qualname__}'
    return f'{handler.__class__.__qualname__}'


_CALLABLE = Callable[[dict[str, Any]], Awaitable[Any]]
def make_mdw_wrapper_factory(
    args_call: Callable[[dict[str, Any]], list[Any]] | None = None,
    next_call_arg_name: str = 'next_call'
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