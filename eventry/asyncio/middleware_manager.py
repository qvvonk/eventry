from __future__ import annotations


__all__ = [
    'MiddlewareManager',
    'MiddlewareWrappedCallable',
    'MiddlewaresExecutor',
    'MiddlewareManagerTypes',
]


from typing import Literal
from dataclasses import dataclass
from enum import Enum, auto
from collections import deque
from collections.abc import Iterable, Iterator, Sequence, Awaitable, Generator, AsyncGenerator

from typing_extensions import Any, Union, Generic, TypeVar, Callable, overload

from eventry.exceptions import Return, FinalizingError, _EarlyFinalized
from eventry.asyncio.default_types import MiddlewareType

from .callable_wrappers import CallableWrapper, MiddlewareCallable


MiddlewareTypeT = TypeVar('MiddlewareTypeT', bound=MiddlewareType, default=MiddlewareType)
R = TypeVar('R', default=Any)


class MiddlewareManagerTypes(Enum):
    MANAGER_OUTER = auto()
    MANAGER_INNER = auto()
    HANDLING_PROCESS = auto()
    OUTER_PER_HANDLER = auto()
    INNER_PER_HANDLER = auto()


class MiddlewareWrappedCallable(Generic[R]):
    def __init__(
        self,
        __callable: Union[Callable[..., Union[Awaitable[R], R]], CallableWrapper[R]],
        /,
        middlewares: Iterable[CallableWrapper],
    ) -> None:
        self._callable = (
            __callable if isinstance(__callable, CallableWrapper) else CallableWrapper(__callable)
        )
        self._middlewares = middlewares

    @overload
    async def __call__(
        self,
        callable_args: Sequence[Any],
        middlewares_args: Sequence[Any],
        data: dict[str, Any],
        executor: MiddlewaresExecutor | None = None,
        finalize_on_callable_exception: bool = True,
        finalize: Literal[False] = False,
    ) -> R | None: ...

    @overload
    async def __call__(
        self,
        callable_args: Sequence[Any],
        middlewares_args: Sequence[Any],
        data: dict[str, Any],
        executor: MiddlewaresExecutor | None = None,
        finalize_on_callable_exception: bool = True,
        finalize: Literal[True] = True,
    ) -> Any: ...

    async def __call__(
        self,
        callable_args: Sequence[Any],
        middlewares_args: Sequence[Any],
        data: dict[str, Any],
        executor: MiddlewaresExecutor | None = None,
        finalize_on_callable_exception: bool = True,
        finalize: bool = True,
    ) -> R | None:
        """
        Execute the wrapped callable with the provided middlewares.

        This method runs in three stages:

        1. **Middleware pre-processing**: Executes the first part of all middlewares.
           If an exception occurs during this stage, all already started middlewares
           are finalized. If all finalizers complete without errors, `_EarlyFinalized` is
           raised with the original exception in `__cause__`.

        2. **Callable execution**: Calls the original callable wrapped by this object.
           If an exception occurs during execution, all middlewares are finalized,
           and `_EarlyFinalized` is raised with the original exception in `__cause__`.

        3. **Middleware finalization**: If `finalize` is True, finalizes all middlewares
           after callable execution. If an exception occurs during finalization, it is
           wrapped in `FinalizingError` with `callable_return` containing the result
           of the callable, and the original exception set as `__cause__`.

        :param callable_args: Positional arguments for the wrapped callable.
        :param middlewares_args: Positional arguments for all middlewares.
        :param data: Shared dictionary passed to middlewares and the callable.
        :param executor: Optional `MiddlewaresExecutor` instance to manage middleware
                         execution. If None, a new executor is created.
        :param finalize_on_callable_exception: Whether to finalize middlewares if an
            exception occurred while executing wrapped callable.
        :param finalize: Whether to finalize middlewares after callable execution.

        :return: The result of wrapped callable, if `finalize` is `False`, otherwise the return
        of the last finalizer.

        :raises _EarlyFinalized: Raised if the middleware throws an exception during pre-processing,
                            and all finalizers ran without errors.
        :raises FinalizingError: Raised if an exception occurs during middleware finalization.
        :raises Exception: If an exception occurred during callable execution and
            `finalize_on_callable_exception` is `False`.
        """
        executor = executor or MiddlewaresExecutor()
        executor.add_middlewares(*self._middlewares)

        await executor.execute_middlewares(middlewares_args, data)

        try:
            result = await self._callable(callable_args, data)
        except Exception as e:
            if not finalize_on_callable_exception:
                raise
            await executor.finalize_middlewares(exception=e)
            raise _EarlyFinalized from e

        if not finalize:
            return result

        return await executor.finalize_middlewares(result)


@dataclass
class MiddlewaresExecutor:
    """
    Middlewares executor.
    """

    def __init__(self, middlewares: Iterable[CallableWrapper] | None = None) -> None:
        self.middlewares = (
            [i if isinstance(i, CallableWrapper) else CallableWrapper(i) for i in middlewares]
            if middlewares
            else []
        )
        self._middleware_index: int = 0
        self._to_finalize: deque[Generator[Any, Any, Any] | AsyncGenerator[Any, Any]] = deque()
        self._finalized: bool = False

    def __iter__(self) -> MiddlewaresExecutor:
        return self

    def __next__(self) -> CallableWrapper[Any]:
        if self._middleware_index >= len(self.middlewares):
            raise StopIteration
        middleware = self.middlewares[self._middleware_index]
        self._middleware_index += 1
        return middleware

    @property
    def middleware_index(self) -> int:
        return self._middleware_index

    def add_middlewares(self, *middlewares: Callable[..., Any] | CallableWrapper[Any]) -> None:
        for i in middlewares:
            self.middlewares.append(i if isinstance(i, CallableWrapper) else CallableWrapper(i))

    async def execute_middlewares(
        self,
        middlewares_args: Sequence[Any],
        data: dict[str, Any],
    ) -> None:
        """
        Execute the first part of all middlewares (up to the first `yield` or return).

        If the `Return` exception was raised, passes value from it to the first finalizer
        and finalizes all "opened" middlewares.

        If an error occurs while executing, finalizes all "opened" middlewares by running
        their second part (after `yield`) and throws the original exception into them.

        If none of the finalizers handle the exception, the original exception is raised.
        If after the finalization process an unhandled exception remains, raises
        `FinalizingError` with it in `__cause__`.

        If all finalizers complete without errors, raises `_EarlyFinalized` with the original
        exception in `__cause__` (including `Return` exception).

        :param middlewares_args: Positional arguments to pass to each middleware.
        :param data: Dictionary containing data to pass to middlewares. Updated with
                     middleware results if they return a dict.

        :raises _EarlyFinalized: If an exception occurs during middleware execution and
            all finalizers succeed.

        :raises FinalizingError: If an exception occurs during finalization.
        """
        try:
            for curr_middleware in self:
                gen = await curr_middleware(middlewares_args, data)
                try:
                    if isinstance(gen, (Generator, AsyncGenerator)):
                        r = next(gen) if isinstance(gen, Generator) else await anext(gen)
                        self._to_finalize.appendleft(gen)
                    else:
                        r = gen
                except (StopIteration, StopAsyncIteration, Return) as e:
                    r = e.value if isinstance(e, (StopIteration, Return)) else None
                if isinstance(r, dict):
                    data.update(r)
        except Exception as e:
            await self.finalize_middlewares(exception=e)
            raise _EarlyFinalized from e

    async def finalize_middlewares(
        self,
        value: Any = None,
        exception: Exception | None = None,
    ) -> Any:
        """
        Finalize all started middlewares by executing the second part of generators
        (code after `yield`) in reverse order of their start.

        Sending `value` to the first middleware to finalize.

        The returned value of the current finalizer will be sent to the next finalizer. But this
        works only for synchronous middlewares.
        For async middlewares raise `Return(value)` exception to return a value.

        If a finalizer raises a `Return` exception, the value from it will be sent to the following
        finalizer, instead of the original `wrapped_callable_return`.

        If an exception is provided, it will be thrown to the first finalizer. If this finalizer
        is not handling it, it will be propagated to the next finalizer and so on.

        After all middlewares are finalized, if there is an unhandled exception remaining,
        `FinalizingError` will be raised with it in `__cause__`.

        :param value: The value returned by the callable,
        that was wrapped by the middlewares.

        :param exception: Optional exception to throw into middleware generators
            during finalization.

        :raises FinalizingError: If an exception occurred during finalization,
            and it *was not handled* by the following finalizers.

        :returns: The return value of the last finalizer or original `value` if there were
        no middlewares to finalize.
        """
        while self._to_finalize:
            gen = self._to_finalize.popleft()
            try:
                if isinstance(gen, Generator):
                    gen.throw(exception) if exception is not None else gen.send(value)
                elif isinstance(gen, AsyncGenerator):
                    await gen.athrow(exception) if exception is not None else await gen.asend(
                        value,
                    )
                exception = None
            except (StopAsyncIteration, StopIteration, Return) as e:
                exception = None
                value = e.value if isinstance(e, (StopIteration, Return)) else None
            except Exception as e:
                exception = e

        if exception is not None:
            raise FinalizingError from exception
        return value


class MiddlewareManager(Generic[MiddlewareTypeT], Sequence[MiddlewareCallable[Any]]):
    def __init__(self) -> None:
        self._middlewares: list[MiddlewareCallable[Any]] = []
        self._inheritable: list[MiddlewareCallable[Any]] = []

    def register_middleware(
        self,
        middleware: MiddlewareTypeT,
        inheritable: bool = False,
    ) -> MiddlewareTypeT:
        m = MiddlewareCallable(middleware, inheritable=inheritable)
        self._middlewares.append(m)
        if m.inheritable:
            self._inheritable.append(m)
        return middleware

    @overload
    def __call__(self, func: MiddlewareTypeT, /) -> MiddlewareTypeT:
        pass

    @overload
    def __call__(
        self,
        /,
        *,
        inheritable: bool = False,
    ) -> Callable[[MiddlewareTypeT], MiddlewareTypeT]:
        pass

    @overload
    def __call__(
        self,
        func: MiddlewareTypeT,
        /,
        *,
        inheritable: bool = False,
    ) -> MiddlewareTypeT:
        pass

    def __call__(
        self,
        func: MiddlewareTypeT | None = None,
        /,
        *,
        inheritable: bool = False,
    ) -> Union[MiddlewareTypeT, Callable[[MiddlewareTypeT], MiddlewareTypeT]]:
        def inner(middleware: MiddlewareTypeT) -> MiddlewareTypeT:
            self.register_middleware(middleware, inheritable=inheritable)
            return middleware

        if func is None:
            return inner
        return inner(func)

    @overload
    def __getitem__(self, index: int) -> MiddlewareCallable[Any]: ...

    @overload
    def __getitem__(self, index: slice) -> list[MiddlewareCallable[Any]]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> MiddlewareCallable[Any] | list[MiddlewareCallable[Any]]:
        return self._middlewares[index]

    def __len__(self) -> int:
        return len(self._middlewares)

    def __bool__(self) -> bool:
        return bool(len(self._middlewares))

    def __reversed__(self) -> Iterator[MiddlewareCallable]:
        return reversed(self._middlewares)

    @property
    def inheritable_middlewares(self) -> tuple[MiddlewareCallable[Any], ...]:
        return tuple(self._inheritable)
