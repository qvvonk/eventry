from __future__ import annotations


__all__ = [
    'HandlerManager',
]


import sys
import time
import asyncio
import inspect
import pathlib
from types import MappingProxyType
from collections.abc import Callable, AsyncGenerator

from typing_extensions import (
    TYPE_CHECKING,
    Any,
    Generic,
    TypeVar,
    Optional,
)

from eventry.config import DispatcherConfig, HandlerManagerConfig
from eventry.loggers import router_logger
from eventry.exceptions import FinalizingError
from eventry.asyncio.filter import Filter, FilterFromFunction, convert_filters
from eventry.asyncio.default_types import FilterType, HandlerType, MiddlewareType
from eventry.asyncio.callable_wrappers import Handler, HandlerMeta, CallableWrapper
from eventry.asyncio.middleware_manager import (
    MiddlewareManager,
    MiddlewaresExecutor,
    MiddlewareManagerTypes,
)


if TYPE_CHECKING:
    from eventry.asyncio.event import Event
    from eventry.asyncio.router.base import Router

    EventFilterCallable = Callable[[Event], bool]
    EventFilter = EventFilterCallable | str


RouterT = TypeVar('RouterT', bound='Router', default='Router')
HandlerT = TypeVar('HandlerT', bound=HandlerType, default=HandlerType)
FilterT = TypeVar('FilterT', bound=FilterType, default=FilterType)
MiddlewareT = TypeVar('MiddlewareT', bound=MiddlewareType, default=MiddlewareType)


DummyFilter = FilterFromFunction(lambda *args: True)


class HandlerManager(Generic[FilterT, HandlerT, MiddlewareT, RouterT]):
    """
    Manages the registration and filtering of event handlers for a specific event type.

    This class acts as a container and dispatcher for `Handler` instances, responsible for:

    - Registering handlers via ``register_handler`` or ``__call__``.
    - Ensuring handler ID uniqueness across the entire router network (global ID deduplication).
    - Filtering handlers based on event type and filter attached to handler.
    - Providing read-only access to all registered handlers.

    Each ``HandlerManager`` is attached to a specific ``Router`` and can optionally be bound to a
    specific ``Event`` subclass via ``event_type_filter``, which restricts dispatching
    to events of that exact type (excluding subclasses).

    Handlers can be registered via ``@manager`` / ``@manager(...)`` decorators.

    :param router: The `Router` instance this manager is associated with.
    :param event_filter: event filter.
    """

    def __init__(
        self,
        router: RouterT,
        name: str,
        event_filter: EventFilter | None = None,
        config: HandlerManagerConfig | None = None,
    ) -> None:
        """
        :param router: `Router` instance this manager is associated with.
        :param name: handler manager name.
        :param event_filter: event name filter.
        :param config: `HandlerManagerConfig` instance.
        """
        self._handlers: dict[str, Handler[Any]] = {}
        self._router = router
        self._event_filter = event_filter
        self._name = name
        self._config = config or HandlerManagerConfig()
        self._middleware_managers: dict[
            MiddlewareManagerTypes,
            MiddlewareManager[MiddlewareT],
        ] = {}

        self._filter: Filter = DummyFilter

    def set_filter(self, filter: FilterT | Filter) -> None:
        self._filter = filter if isinstance(filter, Filter) else FilterFromFunction(filter)

    def remove_filter(self) -> None:
        self._filter = DummyFilter

    def check_event(self, event: Event) -> bool:
        if self.event_filter is None:
            return True
        if isinstance(self.event_filter, str):
            return self.event_filter == event.name

        return self.event_filter(event)

    def _create_handler_obj(
        self,
        handler: HandlerT,
        event_filter: EventFilter | None = None,
        handler_id: str | None = None,
        filter: Optional[FilterT] = None,
        middlewares: list[MiddlewareT] | None = None,
        as_task: bool = False,
        meta: HandlerMeta | None = None,
    ) -> Handler[Any]:
        handler_obj = Handler(
            handler,
            handler_id=handler_id or gen_default_handler_id(handler, self),
            handler_manager=self,
            event_filter=event_filter,
            filter=convert_filters([filter])[0] if filter is not None else None,
            middlewares=[CallableWrapper(i) for i in middlewares]
            if middlewares is not None
            else [],
            as_task=as_task,
            meta=meta or HandlerMeta.from_callable(
                _callable=handler,
                registration_frame=inspect.stack()[1],
            )
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
        root_router = self.router.root_router

        if (exists_handler := root_router.get_handler(handler.id)) is not None:
            raise ValueError(
                f'Handler with ID {handler.id} already exists.\n'
                f"Original handler registered in router '{exists_handler.manager.router.name}':\n"
                f'    Defined in "{exists_handler.meta.definition_filename}:'
                f'{exists_handler.meta.definition_lineno}"\n'
                f'    Registered in {exists_handler.meta.registration_filename}:'
                f'{exists_handler.meta.registration_lineno}\n\n'
                f"Duplicate handler in router '{handler.manager.router.name}':\n"
                f'    Defined in "{handler.meta.definition_filename}:'
                f'{handler.meta.definition_lineno}"\n'
                f'    Registered in {handler.meta.registration_filename}:'
                f'{handler.meta.registration_lineno}',
            )
        self._handlers[handler.id] = handler
        router_logger.info(
            f"[{self.router.name} -> {self.name}] Registered handler '{handler.id}'.",
        )

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

    def _add_middleware_manager(
        self,
        _type: MiddlewareManagerTypes,
        middleware_manager: MiddlewareManager[Any],
    ) -> None:
        if self._middleware_managers.get(_type):
            raise RuntimeError(f'{_type} middleware manager is already exists.')
        self._middleware_managers[_type] = middleware_manager

    def middleware_manager(self, _type: MiddlewareManagerTypes) -> MiddlewareManager[Any] | None:
        return self._middleware_managers.get(_type)

    def collect_middlewares(self, _type: MiddlewareManagerTypes, event: Event) -> list[MiddlewareT]:
        total_middlewares: list[MiddlewareT] = event.__get_inherited_middlewares__(_type)
        middlewares = self.middleware_manager(_type)
        if middlewares is None:
            return total_middlewares

        total_middlewares.extend(middlewares)
        return total_middlewares

    def __call__(
        self,
        filter: Optional[FilterT] = None,
        /,
        *,
        event_filter: EventFilter | None = None,
        handler_id: str | None = None,
        middlewares: list[MiddlewareT] | None = None,
        as_task: bool = False,
    ) -> Callable[[HandlerT], HandlerT]:
        def inner(handler: HandlerT) -> HandlerT:
            meta = HandlerMeta.from_callable(
                handler,
                registration_frame=inspect.stack()[1],
            )
            handler_obj = self._create_handler_obj(
                handler=handler,
                event_filter=event_filter,
                handler_id=handler_id,
                filter=filter,
                middlewares=middlewares,
                as_task=as_task,
                meta=meta
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
    def router(self) -> RouterT:
        """
        An instance of ``Router`` to which this manager is attached.
        :return:
        """
        return self._router

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
        config: DispatcherConfig,
        event: Event,
        event_context: dict[str, Any],
        silent: bool,
    ) -> AsyncGenerator[Exception, None]:
        """
        Executes handling-process middlewares and each handler in this manager
        (every filter, outer-inner-handler middlewares and handler itself).

        If an unhandled exception occurred during executing filter, outer-inner-handler middlewares
        or handler itself - yields it (if `silent` is `False`), otherwise ignores it.

        If an exception occurred during handling-process middlewares execution,
        raises `_EarlyFinalized` exception, if an exception handled by finalizers, otherwise
        yields it.

        For each handler creates a new copy of `event_context` and adds `handler` and `data` keys.

        Returns a generator of exceptions raised during handler execution.
        If `silent` is `True` - no exceptions are yielded.

        :raises _EarlyFinalized: If an error occurred during handling-process middlewares execution,
            but was successfully handled by finalizers.
        """
        middlewares_executor = MiddlewaresExecutor()
        middlewares_executor.add_middlewares(
            *(self.collect_middlewares(MiddlewareManagerTypes.HANDLING_PROCESS, event)),
        )

        try:
            await middlewares_executor.execute_middlewares(
                middlewares_args=self._config.middleware_positional_only_args,
                data=event_context,
            )
        except FinalizingError as e:
            yield e.__cause__
        # except _EarlyFinalized: raise
        # No other exceptions are expected here.

        async for h in self.get_matching_handlers(event):
            event_context = {
                **event_context,
                config.default_names_remap.get('handler', 'handler'): h,
            }
            event_context[config.default_names_remap.get('data', 'data')] = event_context

            try:
                await self._execute_handler(event, h, event_context=event_context)
            except Exception as e:
                if not silent:
                    yield e

            if event.propagation_stopped:
                router_logger.debug(f'({id(event)}) Event propagation stopped.')
                break

        try:
            await middlewares_executor.finalize_middlewares()
        except FinalizingError as e:
            yield e.__cause__
        # No other exceptions are expected here.

    async def _execute_handler(
        self,
        event: Event,
        handler: Handler[Any],
        event_context: dict[str, Any],
    ) -> None:
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
            asyncio.create_task(handler.execute_wrapped(event, data=event_context))
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


def gen_default_handler_id(
    handler: HandlerT,
    manager: HandlerManager[Any, Any, Any, Any],
) -> str:
    is_class_instance = not (
        inspect.isfunction(handler) or inspect.ismethod(handler) or inspect.isclass(handler)
    )

    handler = handler if not is_class_instance else handler.__class__
    func_file = pathlib.Path(inspect.getfile(handler)).resolve()

    main_file = pathlib.Path(sys.modules['__main__'].__file__).resolve()
    project_root = main_file.parent

    try:
        rel_path = func_file.relative_to(project_root).with_suffix('')
    except ValueError:
        rel_path = func_file.with_suffix('')

    module_path = '.'.join(rel_path.parts)

    return f'{manager.router.name}.{manager.name}--{module_path}.{handler.__qualname__}'
