from __future__ import annotations

from typing import TYPE_CHECKING, Any
from types import MappingProxyType
from collections.abc import Iterator


class EventBase:
    if TYPE_CHECKING:
        __event_name__: str

    def __init_subclass__(cls, **kwargs: Any) -> None:
        name = kwargs.pop('event_name', None)

        if not getattr(cls, '__event_name__', None):
            if name is None:
                raise TypeError(
                    f"{cls.__name__} must be defined with keyword argument 'event_name'.",
                )

            if not isinstance(name, str):
                raise ValueError(
                    f'Event name for class {cls.__name__} must be a string, '
                    f'got {type(name).__name__}.',
                )

        if name is not None:
            cls.__event_name__ = name
        super().__init_subclass__(**kwargs)

    @property
    def name(self) -> str:
        return self.__event_name__


class Event(EventBase, event_name='event'):
    """
    Base event class.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._propagation_stopped = False

    def stop_propagation(self) -> None:
        """
        Stop further propagation of this event.

        Once called, the dispatcher will no longer deliver the event
        to subsequent handlers.
        """
        self._propagation_stopped = True

    def context_injection(self) -> dict[str, Any]:
        return {}

    @property
    def propagation_stopped(self) -> bool:
        """
        Check whether the event propagation has been stopped.

        :return: ``True`` if propagation has been stopped, otherwise ``False``.
        """
        return self._propagation_stopped


class ExtendedEvent(Event, event_name='event'):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Extended event class with flags and data features.
        """

        super().__init__(*args, **kwargs)
        self._data: dict[Any, Any] = {}
        self._flags: set[Any] = set()

    def __setitem__(self, key: Any, value: Any) -> None:
        self._data[key] = value

    def __getitem__(self, key: Any) -> Any:
        return self._data[key]

    def __contains__(self, key: Any) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator[Any]:
        return iter(self._data)

    def set_flag(self, flag: Any) -> None:
        self._flags.add(flag)

    def set_flags(self, *flags: Any) -> None:
        self._flags.update(flags)

    def unset_flag(self, flag: Any) -> None:
        if flag in self._flags:
            self._flags.remove(flag)

    def unset_flags(self, *flags: Any) -> None:
        self._flags.difference_update(flags)

    def has_flag(self, flag: Any) -> bool:
        return flag in self._flags

    @property
    def flags(self) -> frozenset[Any]:
        return frozenset(self._flags)

    @property
    def data(self) -> MappingProxyType[Any, Any]:
        return MappingProxyType(self._data)
