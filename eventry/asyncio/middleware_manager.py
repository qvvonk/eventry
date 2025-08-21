from __future__ import annotations


__all__ = [
    'MiddlewareManager',
    'WrappedWithMiddlewaresCallable',
    'CallState',
]


from typing import Any, TypeVar, Callable, Awaitable, overload
from dataclasses import field, dataclass
from functools import wraps
from collections.abc import Sequence

from eventry.asyncio.bases import CallableInfo, MiddlewareCallableType, WrappedWithMiddlewaresType


F = TypeVar('F', bound=MiddlewareCallableType)


@dataclass
class CallState:
    callable_executed: bool = False
    callable_return: Any = None
    local_scope_workflow_data: dict[str, Any] = field(default_factory=dict)


class WrappedWithMiddlewaresCallable:
    """
    A callable object returned by ``MiddlewareManager.wrap_callable_with_middlewares``.

    Represents a handler wrapped in a chain of middleware functions.
    Can be invoked as a regular asynchronous function without arguments (i.e. ``await obj()``).

    On each call, a fresh ``CallState`` instance is created and passed through the middleware
    chain to the original callable.

    The returned ``CallState`` contains information about whether the original callable
    was executed and what it returned.

    :returns: ``CallState`` instance representing the execution state and result.
    """

    def __init__(
        self,
        wrapped_callable: Callable[[CallState], Awaitable[Any]] | None = None,
        /,
    ):
        self._wrapped_callable = wrapped_callable

    async def __call__(self) -> CallState:
        assert self._wrapped_callable is not None

        state = CallState()
        await self._wrapped_callable(state)
        return state


class MiddlewareManager(Sequence[MiddlewareCallableType]):
    def __init__(self) -> None:
        self._middlewares: list[MiddlewareCallableType] = []

    def register_middleware(self, middleware: F) -> F:
        self._middlewares.append(middleware)
        return middleware

    @overload
    def __call__(self, middleware: F, /) -> F: ...

    @overload
    def __call__(self) -> Callable[[F], F]: ...

    def __call__(self, middleware: F | None = None) -> F | Callable[[F], F]:
        if middleware is None:
            return self.register_middleware
        return self.register_middleware(middleware)

    @overload
    def __getitem__(self, index: int) -> MiddlewareCallableType: ...

    @overload
    def __getitem__(self, index: slice) -> list[MiddlewareCallableType]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> MiddlewareCallableType | list[MiddlewareCallableType]:
        return self._middlewares[index]

    def __len__(self) -> int:
        return len(self._middlewares)

    @staticmethod
    def wrap_callable_with_middlewares(
        middlewares: Sequence[MiddlewareCallableType],
        callable_to_wrap: Callable[..., Any],
        workflow_data: dict[str, Any],
        first_to_last: bool = True,
    ) -> WrappedWithMiddlewaresCallable:
        """
        Wraps ``callable_to_wrap`` into middlewares.

        Both middlewares and original callable should be callables (synchronous or asynchronous).
        Internally for all of middlewares and original callable creates a ``CallableInfo`` object,
        that stores info about callable signatures. Thus, both middlewares and original callable can
        accept any set of arguments, ``CallableInfo`` will automatically provide values for them
        from the given ``workflow_data`` when calling
        ``await CallableInfo.__call__(**workflow_data)``.

        Additionally, every middleware can accept ``next_call`` argument, that represents a
        next middleware (or original callable) in the chain of middlewares. If ``next_call`` will
        not be explicitly called via ``await next_call()``, the middleware chain will be
        interrupted.

        Internally, every middleware invocation wrapped in function, that accepts ``CallState`` obj.
        This object will be created by ``WrappedWithMiddlewaresCallable``, when invoked its
        ``__call__`` method.
        The last callable in middlewares chain (original callable) is wrapped in function,
        that executes it and stores its result in ``CallState`` instance.

        :param middlewares: list of middlewares.
        :param callable_to_wrap: callable to wrap.
        :param workflow_data: workflow data, that will be passed to each middleware and
        original callable.

        :param first_to_last: whether the passed ``middlewares`` has order from first middleware
        to the last middleware. If ``True``, will wrap reversely
        (the first middleware is applied last, will be executed first)

        :return: ``WrappedWithMiddlewaresCallable``, that contains wrapped in middlewares
        original callable and can be called with ``async obj()``.
        """

        handler_obj = CallableInfo(callable_to_wrap)

        @wraps(callable_to_wrap)
        async def last_call(state: CallState) -> Any:
            nonlocal handler_obj

            result = await handler_obj(
                **workflow_data | {'local_workflow_data': state.local_scope_workflow_data},
            )

            state.callable_executed = True
            state.callable_return = result

        current: Callable[[CallState], Awaitable[Any]] = last_call

        for middleware in reversed(middlewares) if first_to_last else middlewares:
            current = MiddlewareManager._wrap_with_middleware(current, middleware, workflow_data)

        return WrappedWithMiddlewaresCallable(current)

    @staticmethod
    def _wrap_with_middleware(
        callable_to_wrap: Callable[[CallState], Any],
        middleware: MiddlewareCallableType,
        workflow_data: dict[str, Any],
    ) -> WrappedWithMiddlewaresType:
        middleware_obj = CallableInfo(middleware)

        @wraps(middleware)
        async def wrapped(state: CallState) -> Any:
            nonlocal middleware_obj

            @wraps(callable_to_wrap)
            async def next_call() -> Any:
                return await callable_to_wrap(state)

            result = await middleware_obj(
                **workflow_data
                | {
                    'next_call': next_call,
                    'local_workflow_data': state.local_scope_workflow_data,
                },
            )

            return result

        return wrapped
