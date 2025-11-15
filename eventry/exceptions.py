from __future__ import annotations


__all__ = [
    'Return',
    'EarlyFinalized',
    'FinalizingError',
    'HandlerNotExecuted',
]


from typing_extensions import Any


class Return(Exception):
    pass


class EarlyFinalized(Exception):
    pass


class FinalizingError(Exception):
    def __init__(self, callable_return: Any, *args: Any) -> None:
        super().__init__(*args)
        self._callable_return = callable_return

    @property
    def callable_return(self) -> Any:
        return self._callable_return


class HandlerNotExecuted(Exception):
    pass
