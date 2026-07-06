from __future__ import annotations


__all__ = [
    'HandlerManager',
]

import time
import asyncio
import inspect
from types import MappingProxyType
from collections.abc import Callable, AsyncGenerator

from typing import TYPE_CHECKING, Any, TypeVar

from eventry.loggers import router_logger
from eventry.asyncio.filter import Filter, FilterFromFunction, convert_filters, dummy_filter
from eventry.asyncio.callable_wrappers import Handler
from eventry.config import HandlerManagerConfig


if TYPE_CHECKING:
    from eventry.event import Event

    EventFilterCallable = Callable[[Event], bool]
    EventFilter = EventFilterCallable | str


T = TypeVar('T')


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

        self._filter: Filter = dummy_filter()

    def set_filter(self, filter: Any) -> None:
        self._filter = filter if isinstance(filter, Filter) else FilterFromFunction(filter)

    def remove_filter(self) -> None:
        self._filter = dummy_filter()

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

    async def get_matching_handlers(self, event: Event) -> AsyncGenerator[Handler[Any], None]:
        """
        Iterates through all registered handlers and yields those whose filters
        match the given event.

        :param event: The incoming event to check against handler filters.

        :return: An async generator yielding handlers that should handle the event.
        """

        for handler in self._handlers.values():
            if not handler.check_event(event):
                continue
            yield handler

    def __call__(
        self,
        filter: Any = None, # todo
        /,
        *,
        event_filter: EventFilter | None = None,
        handler_id: str | None = None,
        as_task: bool = False,
    ) -> Callable[[T], T]:
        def inner(handler: T) -> T:
            handler_obj = self._create_handler_obj(
                handler=handler,
                event_filter=event_filter,
                handler_id=handler_id,
                filter=filter,
                as_task=as_task,
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

    async def execute_handlers(
        self,
        event: Event,
        event_context: dict[str, Any],
        handler_result_policy: Any = None,  # todo
    ):
        ...

    async def _execute_handler(
        self,
        event: Event,
        handler: Handler[Any],
        event_context: dict[str, Any]
    ) -> asyncio.Task[Any] | None:
        """
        Executes handler with filter and outer-inner-handler middlewares.

        :raises Exception: If an unhandled exception occurred during executing process, and it was
            not handled by finalizers.
        """
        router_logger.debug(
            '(%d) Executing handler %s -> %s -> %s...',
            id(event),
            self.router.name,
            self.name,
            handler.id,
        )

        start = time.time()
        try:
            if not handler.as_task:
                return await handler.execute_wrapped(event, data=event_context)
            else:
                return asyncio.create_task(
                    handler.execute_wrapped(event, data=event_context),
                    name=f'eventry_handler_task: {handler._handler_id}'
                )
        except FinalizingError as e:
            router_logger.error(
                '(%d) An error occurred while executing handler %s -> %s -> %s.',
                id(event),
                self.router.name,
                self.name,
                handler.id,
                exc_info=e.__cause__,
            )
            raise
        finally:
            stop = time.time() - start
            router_logger.debug(
                "(%d) Handler '%s' executed in %.10f seconds.",
                id(event),
                handler.id,
                stop,
            )


def gen_default_handler_id(handler: Any):
    if inspect.isfunction(handler) or inspect.ismethod(handler) or inspect.isclass(handler):
        return f'{handler.__qualname__}'
    return f'{handler.__class__.__qualname__}'
