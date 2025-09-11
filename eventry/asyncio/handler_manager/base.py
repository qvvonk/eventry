from __future__ import annotations

__all__ = [
    'HandlerManager',
    'MiddlewareManagerTypes',
]


import sys
import inspect
import pathlib
from typing import TYPE_CHECKING, Any, Type, Generic, overload
from abc import ABC
from enum import Enum, auto
from types import MappingProxyType
from collections.abc import Callable

from eventry.config import HandlerManagerConfig
from eventry.loggers import router_logger

from ..filter import _convert_filters
from eventry.asyncio.callable_wrappers import Handler, HandlerMeta
from typing_extensions import Self, TypeVar
from collections.abc import AsyncGenerator
from eventry.asyncio.default_types import HandlerType, FilterType


if TYPE_CHECKING:
    from eventry.asyncio.event import Event
    from eventry.asyncio.router import Router
    from ..middleware_manager import MiddlewareManager, WrappedWithMiddlewaresCallable

HandlerT = TypeVar('HandlerT', bound=HandlerType, default=HandlerType)
FilterT = TypeVar('FilterT', bound=FilterType, default=FilterType)
RouterT = TypeVar('RouterT', bound='Router', default='Router')


class MiddlewareManagerTypes(Enum):
    OUTER = auto()
    INNER = auto()
    PER_HANDLER = auto()


class HandlerManager(Generic[FilterT, HandlerT, RouterT], ABC):
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
    :param event_type_filter:
        Optional ``Event`` type to restrict the handlers managed by this instance.
        If set, only events of this exact type (``type(event) is event_type_filter``)
        will be processed.
    """

    def __init__(
        self,
        router: RouterT,
        handler_manager_id: str,
        event_type_filter: Type[Event] | None = None,
        config: HandlerManagerConfig | None = None,
    ) -> None:
        self._handlers: dict[str, Handler[Any, Any, Self]] = {}
        self._router = router
        self._event_type_filter = event_type_filter
        self._handler_manager_id = handler_manager_id
        self._config = config or HandlerManagerConfig()
        self._middleware_managers: dict[MiddlewareManagerTypes, MiddlewareManager[Any]] = {}

    def register_handler(
        self,
        handler: HandlerT,
        *,
        event_type: Type[Event] | None = None,
        handler_id: str | None = None,
        filter: FilterT | None = None,
        as_task: bool = False,
    ) -> None:
        meta = HandlerMeta.from_callable(handler, registration_frame=inspect.stack()[1])
        handler_obj = self._create_handler_obj(
            handler=handler,
            handler_id=handler_id,
            event_type=event_type,
            filter=filter,
            as_task=as_task,
            meta=meta,
        )
        self._register_handler(handler_obj)

    def _create_handler_obj(
        self,
        handler: HandlerT,
        event_type: Type[Event] | None = None,
        handler_id: str | None = None,
        filter: FilterT | None = None,
        as_task: bool = False,
        meta: HandlerMeta | None = None,
    ) -> Handler[Any, Any, Self]:
        if self._event_type_filter is not None and event_type is not None:
            raise ValueError(
                'Event type specification is not allowed in handler managers with '
                'event type filter.\n',
            )

        handler_obj = Handler(
            handler,
            handler_id=handler_id or gen_default_handler_id(handler, self),
            handler_manager=self,
            filter=_convert_filters(filter)[0] if filter is not None else None,
            as_task=as_task,
            on_event=event_type,
            meta=meta
            or HandlerMeta.from_callable(
                _callable=handler,
                registration_frame=inspect.stack()[1],
            ),
        )
        return handler_obj

    def _register_handler(self, handler: Handler[Any, Any, Self]) -> None:
        """
        Registers handler to this handler manager.

        Before registration, traverses the entire router network (starting from the root router)
        to check for duplicate handler IDs. If a handler with the same ID is found anywhere
        in the network, raises a ``ValueError``.

        :param handler: ``Handler`` instance to register.

        :raises ValueError: if a handler with the same ID already exists in the router network.
        """
        root_router = self.router.root_router

        if (exists_handler := root_router.get_handler_by_id(handler.id)) is not None:
            raise ValueError(
                f'Handler with ID {handler.id} already exists.\n'
                f"Original handler registered in router '{exists_handler.handler_manager.router.id}':\n"
                f'    Defined in "{exists_handler.meta.definition_filename}:'
                f'{exists_handler.meta.definition_lineno}"\n'
                f'    Registered in {exists_handler.meta.registration_filename}:'
                f'{exists_handler.meta.registration_lineno}\n\n'
                f"Duplicate handler in router '{handler.handler_manager.router.id}':\n"
                f'    Defined in "{handler.meta.definition_filename}:'
                f'{handler.meta.definition_lineno}"\n'
                f'    Registered in {handler.meta.registration_filename}:'
                f'{handler.meta.registration_lineno}',
            )
        self._handlers[handler.id] = handler
        router_logger.info(
            f"[{self.router.id} -> {self.id}] Registered handler '{handler.id}'.",
        )

    def get_handler_by_id(self, handler_id: str) -> Handler[Any, Any, Self] | None:
        return self._handlers.get(handler_id, None)

    def remove_handler(self, handler_id: str) -> Handler[Any, Any, Self] | None:
        """
        Removes handler from this handler manager.

        :returns: deleted ``Handler`` instance or ``None``, if ID was not found.
        """
        return self._handlers.pop(handler_id, None)

    async def get_matching_handlers(
        self,
        event: Event,
        single_handler: bool,
        workflow_data: dict[str, Any],
    ) -> AsyncGenerator[tuple[Handler[Any, Any, Self], Exception | None], None]:
        """
        Executes the chain of pre-filter middlewares and yields handlers
        whose filters match the given event.

        :param event: The event object to be checked against handler filters.
        :param workflow_data: A dictionary containing data related to the current workflow.

        :return: An async generator of ``HandlerInfo`` objects with matching filters.
        """
        outer_middlewares_manager = self._middleware_managers.get(MiddlewareManagerTypes.OUTER)

        if not outer_middlewares_manager:
            result: AsyncGenerator[tuple[Handler[Any, Any, Self], Exception | None], None] = self._inner_get_matching_handlers(event, single_handler, workflow_data)
        else:
            wrapped_get_matching_handlers: WrappedWithMiddlewaresCallable[AsyncGenerator[tuple[Handler[Any, Any, Self], Exception | None], None]] = MiddlewareManager.wrap_callable_with_middlewares(
                middlewares=outer_middlewares_manager,
                callable_to_wrap=self._inner_get_matching_handlers,
                workflow_data=workflow_data,
                callable_positional_only_args=(event, single_handler, workflow_data),
                middlewares_positional_only_args=self._config.middleware_positional_only_args,
            )
            state = await wrapped_get_matching_handlers()
            if not state.callable_executed:
                return
            result = state.callable_return

        async for handler, e in result:
            yield handler, e

    async def _inner_get_matching_handlers(
        self,
        event: Event,
        single_handler: bool,
        workflow_data: dict[str, Any],
    ) -> AsyncGenerator[tuple[Handler[Any, Any, Self], Exception | None], None]:
        """
        Iterates through all registered handlers and yields those whose filters
        match the given event.

        :param event: The incoming event to check against handler filters.

        :return: An async generator yielding handlers that should handle the event.
        """

        for handler in self._handlers.values():
            if handler.on_event is not None and type(event) != handler.on_event:
                router_logger.debug(
                    f'Handler manager {self.router.id}.{self.id} '
                    f'skipped handler {handler.id}: '
                    f'event type {type(event)} is not {handler.on_event} '
                    f'(from handler event type filter).',
                )
                continue

            if handler.filter is None:
                router_logger.debug(
                    f'Handler manager {self.router.id}.{self.id} yielded handler '
                    f'{handler.id}: handler has no filter.',
                )
                yield handler, None
                if single_handler:
                    return
                continue

            try:
                filter_result = await handler.filter(**workflow_data)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                router_logger.debug(
                    f'An error occurred in handler manager {self.router.id}.{self.id} while '
                    f'executing filters of handler {handler.id}. An exception yielded.',
                )
                yield handler, e
                continue

            if filter_result:
                router_logger.debug(
                    f'Handler manager {self.router.id}.{self.id} '
                    f'yielded handler {handler.id}: handler filter result is {filter_result}.',
                )
                yield handler, None
                if single_handler:
                    return
            else:
                router_logger.debug(
                    f'Handler manager {self.router.id}.{self.id} '
                    f'skipped handler {handler.id}: handler filter result is {filter_result}.',
                )

    def _add_middleware_manager(
        self,
        _type: MiddlewareManagerTypes,
        middleware_manager: MiddlewareManager[Any],
    ) -> None:
        if self._middleware_managers.get(_type):
            raise RuntimeError(f'{_type} middleware manager is already registered.')
        self._middleware_managers[_type] = middleware_manager

    def middleware_manager(self, _type: MiddlewareManagerTypes) -> MiddlewareManager[Any] | None:
        return self._middleware_managers.get(_type)

    @overload
    def __call__(self, func: HandlerT, /) -> HandlerT: pass

    @overload
    def __call__(
        self,
        *,
        event_type: Type[Event] | None = None,
        handler_id: str | None = None,
        filter: FilterT | None = None,
        as_task: bool = False,
    ) -> Callable[[HandlerT], HandlerT]: pass

    @overload
    def __call__(
        self,
        func: HandlerT,
        /, *,
        event_type: Type[Event] | None = None,
        handler_id: str | None = None,
        filter: FilterT | None = None,
        as_task: bool = False,

    ) -> HandlerT: pass

    def __call__(
        self,
        func: HandlerT | None = None,
        *,
        event_type: Type[Event] | None = None,
        handler_id: str | None = None,
        filter: FilterT | None = None,
        as_task: bool = False,
    ) -> HandlerT | Callable[[HandlerT], HandlerT]:
        def inner(handler: HandlerT) -> HandlerT:
            meta = HandlerMeta.from_callable(
                handler,
                registration_frame=inspect.stack()[2 if func is not None else 1],
            )
            handler_obj = self._create_handler_obj(
                handler=handler,
                handler_id=handler_id,
                event_type=event_type,
                filter=filter,
                as_task=as_task,
                meta=meta,
            )
            self._register_handler(handler_obj)
            return handler

        if func is None:
            return inner
        return inner(func)

    @property
    def handlers(self) -> MappingProxyType[str, Handler[Any, Any, Self]]:
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
    def id(self) -> str:
        return self._handler_manager_id

    @property
    def event_type_filter(self) -> Type[Event] | None:
        return self._event_type_filter


def gen_default_handler_id(
    handler: HandlerT,
    manager: HandlerManager[Any, Any, Any],
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

    return (
        f'{manager.router.id}.{manager.id}--{module_path}.{handler.__qualname__}'
    )
