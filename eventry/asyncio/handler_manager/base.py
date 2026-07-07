from __future__ import annotations


__all__ = [
    'HandlerManager',
]

import inspect
from types import MappingProxyType
from collections.abc import Callable, Generator, Sequence

from typing import TYPE_CHECKING, Any, TypeVar, Literal

import asyncio
from eventry.asyncio.filter import Filter, FilterFromFunction, convert_filters, dummy_filter
from eventry.asyncio.callable_wrappers import Handler
from eventry.config import HandlerManagerConfig
from eventry.asyncio.middleware_manager import MiddlewareManager, MiddlewareManagerType, MiddlewareRegistrar


if TYPE_CHECKING:
    from eventry.event import Event

    EventFilterCallable = Callable[[Event], bool]
    EventFilter = EventFilterCallable | str


T = TypeVar('T')


ManagerScopeMiddlewareTypes = Literal[
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


class HandlerManager:
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
        self.middleware: MiddlewareRegistrar[ManagerScopeMiddlewareTypes] = MiddlewareRegistrar(
            self, ManagerMdwTypes
        )
        self._filter: Filter = dummy_filter()

    def set_filter(self, filter: Any) -> None:
        self._filter = filter if isinstance(filter, Filter) else FilterFromFunction(filter)

    def remove_filter(self) -> None:
        self._filter = dummy_filter()

    def get_middleware_manager(
        self,
        manager_type: ManagerScopeMiddlewareTypes
    ) -> MiddlewareManager | None:
        try:
            mdw_type = MiddlewareManagerType(manager_type)
        except ValueError:
            return None
        return self._middleware_managers.get(mdw_type)

    def set_middleware_manager(
        self,
        manager_type: ManagerScopeMiddlewareTypes,
        manager: MiddlewareManager | None
    ) -> None:
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
        filter: Any = None, # todo
        /,
        *,
        event_filter: EventFilter | None = None,
        handler_id: str | None = None,
        as_task: bool = False,
        inner_middlewares: Sequence[Any] | None = None,
        outer_middlewares: Sequence[Any] | None = None,
    ) -> Callable[[T], T]:
        def inner(handler: T) -> T:
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

    # ---- Big todo ----
    async def execute_handler(
        self,
        handler: Handler[Any],
        args,
        data: dict[str, Any]
    ) -> None:
        middlewares = list(self.get_middleware_manager('handler.inner') or [])
        middlewares.extend(handler.inner_middlewares)
        wrapped = MiddlewareManager.wrap_with_middlewares(middlewares, handler)
        await wrapped(args, data)

    async def execute_handler_with_filter(
        self,
        handler: Handler[Any],
        args,
        data: dict[str, Any]
    ):
        middlewares = list(self.get_middleware_manager('handler.outer') or [])
        middlewares.extend(handler.outer_middlewares)

        async def execute_handler_with_filter_inner():
            r = await handler.filter.execute(args, data)
            if not r:
                return
            await self.execute_handler(handler, args, data)

        wrapped = MiddlewareManager.wrap_with_middlewares(
            middlewares,
            execute_handler_with_filter_inner
        )
        await wrapped()

    async def execute_handlers(self, args, data: dict[str, Any], event) -> None:
        async def execute_handlers_inner():
            r = await self.filter.execute(args, data)
            if not r:
                return

            for handler in self.get_matching_handlers(event.name):
                if handler.as_task:
                    asyncio.create_task(self.execute_handler_with_filter(handler, args, data))
                else:
                    await self.execute_handler_with_filter(handler, args, data)
                if event.propagation_stopped:
                    return

        middlewares = list(self.get_middleware_manager('manager.inner') or [])
        wrapped = MiddlewareManager.wrap_with_middlewares(middlewares, execute_handlers_inner)
        await wrapped()

    async def propagate_event(self, event, args, data):
        async def inner():
            result = await self.filter.execute(args, data)
            if not result:
                return
            await self.execute_handlers(args, data, event)

        middlewares = list(self.get_middleware_manager('manager.outer') or [])
        wrapped = MiddlewareManager.wrap_with_middlewares(middlewares, inner)
        await wrapped()
    # ---- ---- ----


def gen_default_handler_id(handler: Any):
    if inspect.isfunction(handler) or inspect.ismethod(handler) or inspect.isclass(handler):
        return f'{handler.__qualname__}'
    return f'{handler.__class__.__qualname__}'
