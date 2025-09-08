from __future__ import annotations


__all__ = [
    'HandlerManager',
]

import sys
import inspect
import pathlib
from typing import TYPE_CHECKING, Any, Type, Generic, TypeVar, overload
from types import MappingProxyType
from collections.abc import Callable, AsyncGenerator

from eventry.loggers import router_logger
from eventry.asyncio.event import Event
from eventry.config import HandlerManagerConfig
from ..callable_wrappers import Handler, HandlerMeta
from ..filter import _convert_filters
from abc import ABC, abstractmethod
from enum import Enum, auto
import sys

if TYPE_CHECKING:
    from ..router import Router
    from ..filter import Filter
    from ..middleware_manager import MiddlewareManager



EventType = TypeVar('EventType', bound=Any)
HandlerType = TypeVar('HandlerType', bound=Callable[..., Any])
FilterType = TypeVar('FilterType', bound=Filter)


class MiddlewareManagerTypes(Enum):
    OUTER = auto()
    INNER = auto()
    PER_HANDLER = auto()


class HandlerManager(Generic[FilterType, HandlerType], ABC):
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
        router: Router,
        hanlder_manager_id: str,
        event_type_filter: Type[EventType] | None = None,
        config: HandlerManagerConfig | None = None
    ) -> None:
        self._handlers: dict[str, Handler[Any, Any]] = {}
        self._router = router
        self._event_type_filter = event_type_filter
        self._handler_manager_id = hanlder_manager_id
        self._config = config or HandlerManagerConfig()
        self._middleware_managers: dict[MiddlewareManagerTypes, MiddlewareManager] = {}

    def register_handler(
        self,
        handler: HandlerType,
        *,
        event_type: Type[Event] | None = None,
        handler_id: str | None = None,
        filter: FilterType | None = None,
        as_task: bool = False,
    ) -> None:
        meta = HandlerMeta.from_callable(handler, registration_frame=inspect.stack()[1])
        handler_obj = self._create_handler_obj(
            handler=handler,
            handler_id=handler_id,
            event_type=event_type,
            filter=filter,
            as_task=as_task,
            meta=meta
        )
        self._register_handler(handler_obj)

    def _create_handler_obj(
        self,
        handler: HandlerType,
        event_type: Type[Event] | None = None,
        handler_id: str | None = None,
        filter: FilterType | None = None,
        as_task: bool = False,
        meta: HandlerMeta | None = None
    ):
        if self._event_type_filter is not None and event_type is not None:
            raise ValueError(
                f'Event type specification is not allowed in handler managers with '
                f'event type filter.\n'
            )

        handler_obj = Handler(
            handler,
            handler_id=handler_id or gen_default_handler_id(handler, self),
            handler_manager=self,
            filter=_convert_filters(filter)[0] if filter is not None else None,
            as_task=as_task,
            on_event=event_type,
            meta=meta or HandlerMeta.from_callable(
                _callable=handler,
                registration_frame=inspect.stack()[1]
            ),
        )
        return handler_obj


    def _register_handler(self, handler: Handler[Any, Any]) -> None:
        """
        Registers handler to this handler manager.

        Before registration, traverses the entire router network (starting from the root router)
        to check for duplicate handler IDs. If a handler with the same ID is found anywhere
        in the network, raises a ``ValueError``.

        :param handler: ``Handler`` instance to register.

        :raises ValueError: if a handler with the same ID already exists in the router network.
        """
        root_router = self._router.root_router

        if (exists_handler := root_router.get_handler_by_id(handler.handler_id)) is not None:
            raise ValueError(
                f'Handler with ID {handler.handler_id} already exists.\n'
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
        self._handlers[handler.handler_id] = handler
        router_logger.info(
            f'[{self.router.id} -> {self.handler_manager_id}] Registered handler \'{handler.handler_id}\'.',
        )

    def remove_handler(self, handler_id: str) -> Handler[Any, Any] | None:
        """
        Removes handler from this handler manager.

        :returns: deleted ``Handler`` instance or ``None``, if ID was not found.
        """
        return self._handlers.pop(handler_id, None)

    def _add_middleware_manager(
        self,
        _type: MiddlewareManagerTypes,
        middleware_manager: MiddlewareManager
    ) -> None:
        if self._middleware_managers.get(_type):
            raise RuntimeError(f'{_type} middleware manager is already registered.')
        self._middleware_managers[_type] = middleware_manager

    def middleware_manager(self, _type: MiddlewareManagerTypes) -> MiddlewareManager | None:
        return self._middleware_managers.get(_type)

    @overload
    def __call__(self, func: HandlerType, /) -> HandlerType: ...

    @overload
    def __call__(
        self,
        *,
        event_type: Type[Event] | None = None,
        handler_id: str | None = None,
        filter: FilterType | None = None,
        as_task: bool = False,
    ) -> Callable[[HandlerType], HandlerType]: ...

    def __call__(
        self,
        func: HandlerType | None = None,
        *,
        event_type: Type[Event] | None = None,
        handler_id: str | None = None,
        filter: FilterType | None = None,
        as_task: bool = False,
    ) -> HandlerType | Callable[[HandlerType], HandlerType]:
        def inner(handler: HandlerType) -> HandlerType:
            meta = HandlerMeta.from_callable(
                handler,
                registration_frame=inspect.stack()[2 if func is not None else 1]
            )
            handler_obj = self._create_handler_obj(
                handler=handler,
                handler_id=handler_id,
                event_type=event_type,
                filter=filter,
                as_task=as_task,
                meta=meta
            )
            self._register_handler(handler_obj)
            return handler

        if func is None:
            return inner
        return inner(func)

    @property
    def handlers(self) -> MappingProxyType[str, Handler[Any, Any]]:
        """
        A read-only mapping of handler IDs to their corresponding ``Handler`` instances,
        registered in this manager.
        """
        return MappingProxyType(self._handlers)

    @property
    def router(self) -> Router:
        """
        An instance of ``Router`` to which this manager is attached.
        :return:
        """
        return self._router

    @property
    def handler_manager_id(self) -> str:
        return self._handler_manager_id


def gen_default_handler_id(
    handler: HandlerType,
    manager: HandlerManager[Any, Any],
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

    return f'{manager.router.id}.{manager.handler_manager_id}--{module_path}.{handler.__qualname__}'