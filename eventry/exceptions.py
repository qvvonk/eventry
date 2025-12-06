from __future__ import annotations


__all__ = [
    'Return',
    '_EarlyFinalized',
    'FinalizingError',
    'HandlerNotExecuted',
]


from typing_extensions import Any


class Return(Exception):
    pass


class _EarlyFinalized(Exception):
    """
    Internal exception that indicates that middlewares were early, but successfully finalized.
    This happens when an exception occurred in middlewares / callable.
    """
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


class _HandlerFound(Exception): ...


class _SkipRouter(Exception):
    """
    Internal exception that indicates that the current router and all its
    subrouters should be skipped.

    It is used by inner dispatcher methods and will never be propagated outside.
    """


class _ManagerFilterError(Exception):
    """
    Internal exception that indicates that an error occurred during executing manager-level filter.
    It's used by inner dispatcher methods and will never be propagated outside.
    """
