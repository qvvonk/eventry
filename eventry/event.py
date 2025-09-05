from __future__ import annotations

__all__ = ['Event', 'ErrorEvent', 'EventObjectType']


from typing import Any, Generic, TypeVar


EventObjectType = TypeVar('EventObjectType', bound=Any)


class Event(Generic[EventObjectType]):
    def __init__(self, object: EventObjectType) -> None:
        self._object = object
        self._data = {}
        self._propagation_stopped = False
        self._flags = set()

    def __setitem__(self, key: Any, value: Any) -> None:
        self._data[key] = value

    def __getitem__(self, key: Any) -> Any:
        return self._data[key]

    def set_flag(self, flag: str) -> None:
        self._flags.add(flag)

    def unset_flag(self, flag: str) -> None:
        try:
            self._flags.remove(flag)
        except KeyError:
            pass

    def set_flags(self, *flags: str) -> None:
        for i in flags:
            self.set_flag(i)

    def unset_flags(self, *flags: str) -> None:
        for i in flags:
            self.unset_flag(i)

    def flag(self, flag: str) -> bool:
        return flag in self._flags

    def flags(self) -> tuple[str, ...]:
        return tuple(self._flags)

    def stop_propagation(self) -> None:
        self._propagation_stopped = True

    @property
    def propagation_stopped(self) -> bool:
        return self._propagation_stopped

    @property
    def workflow_dict(self) -> dict[str, Any]:
        return {}

    @property
    def object(self) -> EventObjectType:
        return self._object

    def __hash__(self) -> int:
        return id(self)


class ErrorEvent(Event[Exception]):
    def __init__(self, object: Exception) -> None:
        super().__init__(object=object)

    @property
    def workflow_dict(self) -> dict[str, Any]:
        return {'exception': self.object}

    @property
    def exception(self) -> Exception:
        return self.object
