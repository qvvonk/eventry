from __future__ import annotations

from typing import Any
from types import MappingProxyType
from collections.abc import Iterator


_MISSING = object()


class EventBase:
    __event_name__: str

    def __init_subclass__(cls, *, event_name: str | object = _MISSING, **kwargs: Any) -> None:
        if event_name is _MISSING:
            event_name = getattr(cls, '__event_name__', _MISSING)

        if event_name is _MISSING:
            raise TypeError(f"{cls.__name__} must be defined with keyword argument 'event_name'.")

        if not isinstance(event_name, str):
            raise TypeError(f"'event_name' must be a string, not {type(event_name).__name__!r}.")

        if not event_name:
            raise ValueError("'event_name' must not be empty.")

        cls.__event_name__ = event_name
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

    def context_injection(self) -> dict[str, Any]:
        return {}


class ExtendedEvent(Event):
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
