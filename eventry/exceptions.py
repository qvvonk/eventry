from __future__ import annotations


__all__ = [
    'Return',
    '_EarlyFinalized',
    'FinalizingError',
    'HandlerNotExecuted',
]


from typing_extensions import Any


class Return(Exception):
    def __init__(self, _val: Any) -> None:
        self._val = _val

    @property
    def value(self) -> Any:
        return self._val


class _EarlyFinalized(Exception):
    """
    Internal exception that indicates that middlewares were early, but successfully finalized.
    This happens when an exception occurred in middlewares / callable.
    """

    pass


class FinalizingError(Exception):
    __cause__: Exception
    pass


class HandlerNotExecuted(Exception):
    pass


class _HandlerFound(Exception): ...
