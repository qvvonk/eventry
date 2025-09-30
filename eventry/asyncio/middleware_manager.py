from __future__ import annotations


__all__ = [
    'MiddlewareManager',
    'MiddlewareWrappedCallable',
    'MiddlewaresExecutor',
    'MiddlewareManagerTypes',
]


from enum import Enum, auto
from typing import Any, Union, Generic, TypeVar, Callable, overload
from dataclasses import field, dataclass
from collections import deque
from collections.abc import Iterable, Sequence, Awaitable, Generator, AsyncGenerator

from eventry.exceptions import Return, Finalized, FinalizingError
from eventry.asyncio.default_types import MiddlewareType

from .callable_wrappers import CallableWrapper, MiddlewareCallable


MiddlewareTypeT = TypeVar('MiddlewareTypeT', bound=MiddlewareType, default=MiddlewareType)
R = TypeVar('R', default=Any)


class MiddlewareManagerTypes(Enum):
    GLOBAL = auto()
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

    async def __call__(
        self,
        callable_args: Sequence[Any],
        middlewares_args: Sequence[Any],
        data: dict[str, Any],
        executor: MiddlewaresExecutor | None = None,
        finalize: bool = True,
    ) -> R | None:
        """
            Execute the wrapped callable with the provided middlewares.

            This method runs in three stages:

            1. **Middleware pre-processing**: Executes the first part of all middlewares.
               If an exception occurs during this stage, all already started middlewares
               are finalized. If all finalizers complete without errors, `Finalized` is
               raised with the original exception in `__cause__`. If a finalizer raises
               an unhandled exception, that exception is propagated instead.

            2. **Callable execution**: Calls the original callable wrapped by this object.
               If an exception occurs during execution, all middlewares are finalized,
               and `Finalized` is raised with the original exception.

            3. **Middleware finalization**: If `finalize` is True, finalizes all middlewares
               after callable execution. If an exception occurs during finalization, it is
               wrapped in `FinalizingError` with `callable_return` containing the result
               of the callable, and the original exception set as `__cause__`.

            :param callable_args: Positional arguments for the wrapped callable.
            :param middlewares_args: Positional arguments for all middlewares.
            :param data: Shared dictionary passed to middlewares and the callable.
            :param executor: Optional `MiddlewaresExecutor` instance to manage middleware
                             execution. If None, a new executor is created.
            :param finalize: Whether to finalize middlewares after callable execution.

            :return: The result of the wrapped callable, or None if execution was stopped
                     by a middleware raising `Return`.

            :raises Finalized: Raised if a middleware throws an exception during pre-processing,
                                and all finalizers ran without errors.
            :raises FinalizingError: Raised if an exception occurs during middleware
                                     finalization after successful callable execution.
            """
        executor = executor or MiddlewaresExecutor()
        executor.add_middlewares(*self._middlewares)

        try:
            await executor.execute_middlewares(middlewares_args, data)
        except (Return, Finalized) as e:
            raise Finalized from e
        # Just for explicitly
        # Exception goes out (to dispatcher)
        except:
            raise

        try:
            result = await self._callable(callable_args, data)
            if not finalize:
                return result
        except Exception as e:
            await executor.finalize_middlewares(exception=e)
            raise Finalized from e

        try:
            await executor.finalize_middlewares()
            return result
        except Exception as e:
            raise FinalizingError(callable_return=result) from e


@dataclass
class MiddlewaresExecutor:
    """
    Middlewares executor.
    """

    middlewares: list[CallableWrapper] = field(default_factory=list)

    _middleware_index: int = field(init=False, repr=False, default=0)
    _execute_after: deque[Generator[Any, None, Any] | AsyncGenerator[Any, None]] = field(
        init=False,
        repr=False,
        default_factory=deque,
    )

    def __post_init__(self) -> None:
        self.middlewares = [
            i if isinstance(i, CallableWrapper) else CallableWrapper(i) for i in self.middlewares
        ]

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

    @property
    def done(self) -> bool:
        if self._execute_after:
            return False

        if len(self.middlewares) == 0:
            return True

        if self.middleware_index == len(self.middlewares)-1:
            return True

        return False

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

        If an error occurs while executing, finalizes all started middlewares by running
        their second part (after `yield`) and throws the original exception into them.

        If none of the finalizers handle the exception, the original exception is raised.
        If all finalizers complete without errors, raises `Finalized` with the original
        exception in `__cause__`.

        If a `Return` exception is raised during execution of a middleware, all started
        middlewares are finalized and the `Return` exception is propagated.

        :param middlewares_args: Positional arguments to pass to each middleware.
        :param data: Dictionary containing data to pass to middlewares. Updated with
                     middleware results if they return a dict.

        :raises Return: If a middleware explicitly raises `Return`.
        :raises Finalized: If an exception occurs during middleware execution and
                           all finalizers succeed.
        """
        try:
            for curr_middleware in self:
                gen = await curr_middleware(middlewares_args, data)
                if not isinstance(gen, Generator | AsyncGenerator):
                    if isinstance(gen, dict):
                        data.update(gen)
                    continue

                r = next(gen) if isinstance(gen, Generator) else await anext(gen)
                if isinstance(r, dict):
                    data.update(r)
                self._execute_after.appendleft(gen)

        except Return:
            await self.finalize_middlewares()
            raise
        except Exception as e:
            await self.finalize_middlewares(exception=e)
            raise Finalized from e
        finally:
            self.strip()

    async def finalize_middlewares(
        self,
        exception: Exception | None = None
    ) -> None:
        """
        Finalize all started middlewares by executing the second part of generators
        (code after `yield`) in reverse order of their start.

        If an exception is provided, it is thrown into each generator. If a generator
        raises an exception during finalization, it replaces the previous exception
        to be propagated.

        After all generators are finalized, if any exception remains, it is raised.

        :param exception: Optional exception to throw into middleware generators
                          during finalization.
        :raises Exception: Any exception raised by a middleware finalizer that was not
                           handled by earlier finalizers.
        """
        while self._execute_after:
            gen = self._execute_after.popleft()
            try:
                if isinstance(gen, Generator):
                    gen.throw(exception) if exception is not None else next(gen)
                elif isinstance(gen, AsyncGenerator):
                    await gen.athrow(exception) if exception is not None else await anext(gen)
                exception = None
            except (StopIteration, StopAsyncIteration):
                exception = None
            except Exception as e:
                exception = e

        if exception is not None:
            raise exception

    def strip(self) -> None:
        self.middlewares = self.middlewares[:self.middleware_index]


class MiddlewareManager(Generic[MiddlewareTypeT], Sequence[MiddlewareCallable[Any]]):
    def __init__(self) -> None:
        self._middlewares: list[MiddlewareCallable[Any]] = []
        self._inheritable: list[MiddlewareCallable[Any]] = []

    def register_middleware(self, middleware: MiddlewareTypeT, inheritable: bool=False) -> MiddlewareTypeT:
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
        inheritable: bool = False
    ) -> Callable[[MiddlewareTypeT], MiddlewareTypeT]:
        pass

    @overload
    def __call__(
        self,
        func: MiddlewareTypeT,
        /,
        *,
        inheritable: bool = False
    ) -> MiddlewareTypeT:
        pass

    def __call__(
        self,
        func: MiddlewareTypeT | None = None,
        /,
        *,
        inheritable: bool = False
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

    @property
    def inheritable_middlewares(self) -> tuple[MiddlewareCallable[Any], ...]:
        return tuple(self._inheritable)
