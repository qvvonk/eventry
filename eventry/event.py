from __future__ import annotations


__all__ = ['Event', 'ExtendedEvent']


from typing import Any
from types import MappingProxyType


class Event:
    """
    Base event class.
    """

    def __init__(self) -> None:
        self._propagation_stopped = False

    def stop_propagation(self) -> None:
        self._propagation_stopped = True

    @property
    def workflow_injection(self) -> dict[str, Any]:
        """
        Workflow injection.  # todo: docstring
        """
        return {}

    @property
    def propagation_stopped(self) -> bool:
        return self._propagation_stopped


class ExtendedEvent(Event):
    def __init__(self) -> None:
        """
        Extended event class with flags and data features.
        """

        super().__init__()
        self._data: dict[Any, Any] = {}
        self._flags: set[Any] = set()

    def __setitem__(self, key: Any, value: Any) -> None:
        self._data[key] = value

    def __getitem__(self, key: Any) -> Any:
        return self._data[key]

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
    def flags(self) -> frozenset[Any]:  # todo: optimization for big sets?
        return frozenset(self._flags)

    @property
    def data(self) -> MappingProxyType[Any, Any]:
        return MappingProxyType(self._data)
