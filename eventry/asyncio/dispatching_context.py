from __future__ import annotations


__all__ = [
    'ArgumentSlots',
    'DispatchingContext',
    'HandlerArgumentSlots',
    'ManagerArgumentSlots',
    'RouterArgumentSlots',
]


from typing import TYPE_CHECKING, Any, TypeVar
from dataclasses import field, fields, dataclass
from copy import copy
from collections.abc import Mapping, Iterator, MutableMapping


if TYPE_CHECKING:
    from _typeshed import DataclassInstance

    from eventry.asyncio.event import Event
    from eventry.asyncio.router import Router
    from eventry.asyncio.dispatcher import Dispatcher
    from eventry.asyncio.callable_wrappers import Handler
    from eventry.asyncio.handler_manager.base import HandlerManagerAnyType

    _T = TypeVar('_T', bound=DataclassInstance)


class _MissingType: ...


_MISSING = _MissingType()


@dataclass(slots=True)
class BaseArgumentSlots:
    outer: list[Any] = field(default_factory=list)
    filter: list[Any] = field(default_factory=list)
    inner: list[Any] = field(default_factory=list)

    def copy(self: _T) -> _T:
        return self.__class__(
            **{f.name: copy(getattr(self, f.name)) for f in fields(self) if f.init}
        )


@dataclass(slots=True)
class RouterArgumentSlots(BaseArgumentSlots): ...


@dataclass(slots=True)
class ManagerArgumentSlots(BaseArgumentSlots): ...


@dataclass(slots=True)
class HandlerArgumentSlots(BaseArgumentSlots):
    call: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class ArgumentSlots:
    router: RouterArgumentSlots = field(default_factory=RouterArgumentSlots)
    manager: ManagerArgumentSlots = field(default_factory=ManagerArgumentSlots)
    handler: HandlerArgumentSlots = field(default_factory=HandlerArgumentSlots)

    def copy(self) -> ArgumentSlots:
        return ArgumentSlots(
            router=self.router.copy(),
            manager=self.manager.copy(),
            handler=self.handler.copy(),
        )


class DispatchingContext(MutableMapping[str, Any]):
    _EVENT_KEY = 'event'
    _DISPATCHER_KEY = 'dispatcher'
    _ROUTER_KEY = 'router'
    _MANAGER_KEY = 'manager'
    _HANDLER_KEY = 'handler'
    _ARGUMENTS_KEY = 'argument_slots'
    _RESERVED_KEYS = frozenset(
        {
            _EVENT_KEY,
            _DISPATCHER_KEY,
            _ROUTER_KEY,
            _MANAGER_KEY,
            _HANDLER_KEY,
            _ARGUMENTS_KEY,
        },
    )

    def __init__(
        self,
        *,
        event: Event,
        dispatcher: Dispatcher,
        router: Router[Any],
        data: Mapping[str, Any] | None = None,
        manager: HandlerManagerAnyType | None = None,
        handler: Handler[Any] | None = None,
        arguments: ArgumentSlots | None = None,
    ) -> None:
        self._data = dict(data) if data is not None else {}
        reserved_keys = self._data.keys() & self._RESERVED_KEYS
        if reserved_keys:
            keys = ', '.join(repr(key) for key in sorted(reserved_keys))
            raise ValueError(f'Data contains reserved dispatching context keys: {keys}.')

        self._event = event
        self._dispatcher = dispatcher
        self._router = router
        self._manager = manager
        self._handler = handler
        self._arguments = arguments if arguments is not None else ArgumentSlots()

    @property
    def event(self) -> Event:
        return self._event

    @property
    def dispatcher(self) -> Dispatcher:
        return self._dispatcher

    @property
    def router(self) -> Router[Any]:
        return self._router

    @property
    def manager(self) -> HandlerManagerAnyType | None:
        return self._manager

    @property
    def handler(self) -> Handler[Any] | None:
        return self._handler

    @property
    def args(self) -> ArgumentSlots:
        return self._arguments

    def __getitem__(self, key: str) -> Any:
        if key == self._EVENT_KEY:
            return self.event
        if key == self._DISPATCHER_KEY:
            return self.dispatcher
        if key == self._ROUTER_KEY:
            return self.router
        if key == self._ARGUMENTS_KEY:
            return self.args
        if key == self._MANAGER_KEY and self.manager is not None:
            return self.manager
        if key == self._HANDLER_KEY and self.handler is not None:
            return self.handler
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self._RESERVED_KEYS:
            raise KeyError(
                f'{key!r} is a reserved dispatching context key; '
                f'use DispatchingContext.fork() to replace dispatching metadata.',
            )
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        if key in self._RESERVED_KEYS:
            raise KeyError(f'Cannot delete reserved dispatching context key {key!r}.')
        del self._data[key]

    def __iter__(self) -> Iterator[str]:
        yield self._EVENT_KEY
        yield self._DISPATCHER_KEY
        yield self._ROUTER_KEY
        yield self._ARGUMENTS_KEY
        if self.manager is not None:
            yield self._MANAGER_KEY
        if self.handler is not None:
            yield self._HANDLER_KEY
        yield from self._data

    def __len__(self) -> int:
        metadata_length = 4
        metadata_length += self.manager is not None
        metadata_length += self.handler is not None
        return metadata_length + len(self._data)

    def __copy__(self) -> DispatchingContext:
        return self.fork()

    def copy(self) -> DispatchingContext:
        return self.fork()

    def fork(
        self,
        updates: Mapping[str, Any] | None = None,
        *,
        router: Router[Any] | _MissingType = _MISSING,
        manager: HandlerManagerAnyType | None | _MissingType = _MISSING,
        handler: Handler[Any] | None | _MissingType = _MISSING,
        arguments: ArgumentSlots | None = None,
    ) -> DispatchingContext:
        data = self._data.copy()
        if updates is not None:
            reserved_keys = updates.keys() & self._RESERVED_KEYS
            if reserved_keys:
                keys = ', '.join(repr(key) for key in sorted(reserved_keys))
                raise ValueError(
                    f'Updates contain reserved dispatching context keys: {keys}; '
                    f'use the corresponding fork() keyword arguments instead.',
                )
            data.update(updates)

        return type(self)(
            event=self.event,
            dispatcher=self.dispatcher,
            data=data,
            router=router if not isinstance(router, _MissingType) else self.router,
            manager=manager if not isinstance(manager, _MissingType) else self.manager,
            handler=handler if not isinstance(handler, _MissingType) else self._handler,
            arguments=self.args.copy() if arguments is None else arguments,
        )

    @classmethod
    def from_mapping(cls, data: MutableMapping[str, Any]) -> DispatchingContext:
        if isinstance(data, DispatchingContext):
            return data

        for i in [cls._DISPATCHER_KEY, cls._ROUTER_KEY, cls._EVENT_KEY]:
            if i not in data:
                raise ValueError(f'{i!r} not found.')

        return DispatchingContext(
            event=data.pop(cls._EVENT_KEY),
            dispatcher=data.pop(cls._DISPATCHER_KEY),
            router=data.pop(cls._ROUTER_KEY),
            manager=data.pop(cls._MANAGER_KEY, None),
            handler=data.pop(cls._HANDLER_KEY, None),
            arguments=data.pop(cls._ARGUMENTS_KEY, None),
            data=data,
        )
