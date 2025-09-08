from __future__ import annotations


__all__ = [
    'MiddlewareManager',
    'WrappedWithMiddlewaresCallable',
    'CallState',
]


from typing import Any, Generic, TypeVar, Callable, Awaitable, overload
from dataclasses import field, dataclass
from functools import wraps
from collections.abc import Sequence

from eventry.config import FromKwargs, DefaultNamesRemap

from .callable_wrappers import CallableWrapper


MiddlewareType = TypeVar('MiddlewareType', bound=Callable[..., Any])
F = TypeVar('F', bound=MiddlewareType)
R = TypeVar('R', bound=Any)


@dataclass
class CallState(Generic[R]):
    _callable_executed: bool = False
    _callable_return: R | None = None
    _local_scope_workflow_data: dict[str, Any] = field(default_factory=dict)

    @property
    def callable_executed(self) -> bool:
        return self._callable_executed

    @property
    def callable_return(self) -> R | None:
        if not self.callable_executed:
            raise RuntimeError('Callable is not executed yet.')
        return self._callable_return

    @property
    def local_scope_workflow_data(self) -> dict[str, Any]:
        return self._local_scope_workflow_data


class WrappedWithMiddlewaresCallable(Generic[R]):
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
        wrapped_callable: Callable[[CallState[R]], Awaitable[Any]] | None = None,
        /,
    ):
        self._wrapped_callable = wrapped_callable

    async def __call__(self) -> CallState[R]:
        assert self._wrapped_callable is not None

        state: CallState[R] = CallState()
        await self._wrapped_callable(state)
        return state


class MiddlewareManager(Generic[MiddlewareType], Sequence[MiddlewareType]):
    def __init__(self) -> None:
        self._middlewares: list[MiddlewareType] = []

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
    def __getitem__(self, index: int) -> MiddlewareType: ...

    @overload
    def __getitem__(self, index: slice) -> list[MiddlewareType]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> MiddlewareType | list[MiddlewareType]:
        return self._middlewares[index]

    def __len__(self) -> int:
        return len(self._middlewares)

    @staticmethod
    def wrap_callable_with_middlewares(
        middlewares: Sequence[MiddlewareType],
        callable_to_wrap: Callable[..., R],
        workflow_data: dict[str, Any],
        callable_positional_only_args: tuple[str, ...],
        middlewares_positional_only_args: tuple[str, ...],
        first_to_last: bool = True,
        default_names_remap: DefaultNamesRemap | None = None,
    ) -> WrappedWithMiddlewaresCallable[R]:
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
        default_names_remap = default_names_remap or {}
        wrapped_callable = CallableWrapper(callable_to_wrap)

        @wraps(callable_to_wrap)
        async def last_call(state: CallState[R]) -> Any:
            nonlocal wrapped_callable
            kwargs = workflow_data | {
                default_names_remap.get(
                    'local_workflow_data', 'local_workflow_data'
                ): state.local_scope_workflow_data,
            }
            args = tuple(
                kwargs[i.name] if isinstance(i, FromKwargs) else i
                for i in callable_positional_only_args
            )
            result = await wrapped_callable(args, kwargs)

            state._callable_executed = True
            state._callable_return = result

        current: Callable[[CallState[R]], Awaitable[Any]] = last_call

        for middleware in reversed(middlewares) if first_to_last else middlewares:
            current = MiddlewareManager._wrap_with_middleware(
                current,
                middleware,
                middlewares_positional_only_args,
                workflow_data,
                default_names_remap,
            )

        return WrappedWithMiddlewaresCallable(current)

    @staticmethod
    def _wrap_with_middleware(
        next_middleware_to_wrap: Callable[[CallState[R]], Any],
        middleware: MiddlewareType,
        positional_only_args: tuple[str, ...],
        workflow_data: dict[str, Any],
        default_names_remap: DefaultNamesRemap,
    ) -> Callable[[CallState[R]], Awaitable[Any]]:
        middleware_obj = CallableWrapper(middleware)

        @wraps(middleware)
        async def wrapped(state: CallState[R]) -> Any:
            nonlocal middleware_obj

            @wraps(next_middleware_to_wrap)
            async def next_call() -> Any:
                return await next_middleware_to_wrap(state)

            kwargs = workflow_data | {
                default_names_remap.get('next_call', 'next_call'): next_call,
                default_names_remap.get(
                    'local_workflow_data', 'local_workflow_data'
                ): state.local_scope_workflow_data,
            }
            args = tuple(
                kwargs[i.name] if isinstance(i, FromKwargs) else i for i in positional_only_args
            )

            result = await middleware_obj(args, kwargs)
            return result

        return wrapped
