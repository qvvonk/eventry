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
from eventry.asyncio.bases import HandlerInfo, HandlerMeta, CallableInfo, HandlerCallableType
from eventry.asyncio.event import Event
from eventry.asyncio.filters import Filter, CallableFilter, AwaitableFilter
from eventry.asyncio.middleware_manager import MiddlewareManager


if TYPE_CHECKING:
    from eventry.asyncio.bases import MiddlewareCallableType
    from eventry.asyncio.router import Router


EventType = TypeVar('EventType', bound=Any)
F = TypeVar('F', bound=HandlerCallableType)


class HandlerManager(Generic[EventType]):
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
        name: str,
        event_type_filter: Type[EventType] | None = None,
    ) -> None:
        self._handlers: dict[str, HandlerInfo] = {}
        self._router = router
        self._event_type_filter = event_type_filter
        self._name = name

        self._filtering_middlewares = MiddlewareManager()
        self._handler_middlewares = MiddlewareManager()

    def register_handler(
        self,
        handler: HandlerCallableType,
        *,
        event_type: Type[Event[Any]] | None = None,
        name: str | None = None,
        filter: Filter | CallableFilter | AwaitableFilter | None = None,
        as_task: bool = False,
        middlewares: list[Any] | None = None,
        ensure_after: dict[str, Any] | None = None,
        meta: HandlerMeta | None = None,
    ) -> None:
        if self.event_type_filter is not None and event_type is not None:
            raise ValueError(
                f'Event type specification is not allowed in handler managers with '
                f'event type filter.\n'
            )

        handler_obj = HandlerInfo(
            name=name or gen_default_handler_id(handler, self),
            event_type_filter=event_type,
            filter=CallableInfo(filter) if filter is not None else None,
            as_task=as_task,
            callable=handler,
            manager=self,
            middlewares=middlewares or [],
            ensure_after=ensure_after or {},
            meta=meta
            or HandlerMeta.from_callable(
                callable=handler,
                registration_frame=inspect.stack()[1],
            ),
        )
        self._register_handler(handler_obj)

    def _register_handler(self, handler: HandlerInfo) -> None:
        """
        Registers handler to this handler manager.

        Before registration, traverses the entire router network (starting from the root router)
        to check for duplicate handler IDs. If a handler with the same ID is found anywhere
        in the network, raises a ``ValueError``.

        :param handler: ``Handler`` instance to register.

        :raises ValueError: if a handler with the same ID already exists in the router network.
        """
        root_router = self._router.root_router

        if (exists_handler := root_router.get_handler_by_id(handler.name)) is not None:
            raise ValueError(
                f'Handler with ID {handler.name} already exists.\n'
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
        self._handlers[handler.name] = handler
        router_logger.info(
            f'{self.router.name}.{self.name} Registered handler with ID {handler.name}.',
        )

    def remove_handler(self, handler_id: str) -> HandlerInfo | None:
        """
        Removes handler from this handler manager.

        :returns: deleted ``Handler`` instance or ``None``, if ID was not found.
        """
        return self._handlers.pop(handler_id, None)

    async def get_matching_handlers(
        self,
        event: Event[Any],
        workflow_data: dict[str, Any],
    ) -> AsyncGenerator[tuple[HandlerInfo, Exception | None], None]:
        """
        Executes the chain of pre-filter middlewares and yields handlers
        whose filters match the given event.

        :param event: The event object to be checked against handler filters.
        :param workflow_data: A dictionary containing data related to the current workflow.

        :return: An async generator of ``HandlerInfo`` objects with matching filters.
        """

        async def wrapped() -> AsyncGenerator[tuple[HandlerInfo, Exception | None], None]:
            return self._inner_get_matching_handlers(event, workflow_data)

        wrapped_get_matching_handlers = MiddlewareManager.wrap_callable_with_middlewares(
            middlewares=self._filtering_middlewares,
            callable_to_wrap=wrapped,
            workflow_data=workflow_data,
        )

        middlewares_result = await wrapped_get_matching_handlers()
        if middlewares_result.callable_executed:
            async for handler, e in middlewares_result.callable_return:
                yield handler, e

    async def _inner_get_matching_handlers(
        self,
        event: Event[Any],
        workflow_data: dict[str, Any],
    ) -> AsyncGenerator[tuple[HandlerInfo, Exception | None], None]:
        """
        Iterates through all registered handlers and yields those whose filters
        match the given event.

        :param event: The incoming event to check against handler filters.

        :return: An async generator yielding handlers that should handle the event.
        """

        for handler in self._handlers.values():
            if handler.event_type_filter is not None and type(event) != handler.event_type_filter:
                router_logger.debug(
                    f'Handler manager {self.router.name}.{self.name} '
                    f'skipped handler {handler.name}: '
                    f'event type {type(event)} is not {handler.event_type_filter} '
                    f'(from handler event type filter).',
                )
                continue

            if handler.filter is None:
                router_logger.debug(
                    f'Handler manager {self.router.name}.{self.name} yielded handler '
                    f'{handler.name}: handler has no filter.',
                )
                yield handler, None
                continue

            try:
                filter_result = await handler.filter(**workflow_data)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                router_logger.debug(
                    f'An error occurred in handler manager {self.router.name}.{self.name} while '
                    f'executing filters of handler {handler.name}. An exception yielded.',
                )
                yield handler, e
                continue

            if filter_result:
                router_logger.debug(
                    f'Handler manager {self.router.name}.{self.name} '
                    f'yielded handler {handler.name}: handler filter result is {filter_result}.',
                )
                yield handler, None
            else:
                router_logger.debug(
                    f'Handler manager {self.router.name}.{self.name} '
                    f'skipped handler {handler.name}: handler filter result is {filter_result}.',
                )

    @overload
    def __call__(self, func: F, /) -> F: ...

    @overload
    def __call__(
        self,
        *,
        event_type: Type[Event[Any]] | None = None,
        name: str | None = None,
        filter: Filter | CallableFilter | AwaitableFilter | None = None,
        as_task: bool = False,
        middlewares: list[MiddlewareCallableType] | None = None,
        ensure_after: dict[str, Any] | None = None,
    ) -> Callable[[F], F]: ...

    def __call__(
        self,
        func: F | None = None,
        *,
        event_type: Type[Event[Any]] | None = None,
        name: str | None = None,
        filter: Filter | CallableFilter | AwaitableFilter | None = None,
        as_task: bool = False,
        middlewares: list[MiddlewareCallableType] | None = None,
        ensure_after: dict[str, Any] | None = None,
    ) -> F | Callable[[F], F]:
        def inner(handler: F) -> F:
            self.register_handler(
                handler=handler,
                event_type=event_type,
                name=name,
                filter=filter,
                as_task=as_task,
                middlewares=middlewares,
                ensure_after=ensure_after,
                meta=HandlerMeta.from_callable(
                    callable=handler,
                    registration_frame=inspect.stack()[2 if func is not None else 1],
                ),
            )
            return handler

        if func is None:
            return inner
        return inner(func)

    @property
    def handlers(self) -> MappingProxyType[str, HandlerInfo]:
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
    def event_type_filter(self) -> Type[Event[Any]] | None:
        return self._event_type_filter

    @property
    def name(self) -> str:
        return self._name

    @property
    def filtering_middlewares(self) -> MiddlewareManager:
        return self._filtering_middlewares

    @property
    def handler_middlewares(self) -> MiddlewareManager:
        return self._handler_middlewares


def gen_default_handler_id(
    handler: HandlerCallableType,
    manager: HandlerManager[Any],
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
