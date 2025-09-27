from __future__ import annotations


__all__ = [
    'MiddlewareManager',
    'MiddlewareWrappedCallable',
    'MiddlewaresExecutor',
]


from typing import Any, Union, Generic, TypeVar, Callable, overload
from dataclasses import field, dataclass
from contextlib import suppress
from collections import deque
from collections.abc import Iterable, Sequence, Awaitable, Generator, AsyncGenerator

from eventry.exceptions import AbortExecution, HandlerNotExecuted
from eventry.asyncio.default_types import MiddlewareType

from .callable_wrappers import CallableWrapper


MiddlewareTypeT = TypeVar('MiddlewareTypeT', bound=MiddlewareType, default=MiddlewareType)
R = TypeVar('R', default=Any)


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
        execute_post_middlewares: bool = True,
        close_on_error: bool = True,
    ) -> R:
        executor = executor or MiddlewaresExecutor()
        executor.add_middlewares(*self._middlewares)

        try:
            await executor.execute_pre_middlewares(middlewares_args, data)
        except Exception as e:
            if close_on_error:
                await executor.close()
            if isinstance(e, AbortExecution):
                raise HandlerNotExecuted
            raise

        try:
            result = await self._callable(callable_args, data)
            if execute_post_middlewares:
                await executor.execute_post_middlewares()
        finally:
            if close_on_error:
                await executor.close()

        return result


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
    def execute_after(self) -> deque[Generator[Any, None, Any] | AsyncGenerator[Any, None]]:
        return self._execute_after

    @property
    def middleware_index(self) -> int:
        return self._middleware_index

    def add_middlewares(self, *middlewares: Callable[..., Any] | CallableWrapper[Any]) -> None:
        for i in middlewares:
            self.middlewares.append(i if isinstance(i, CallableWrapper) else CallableWrapper(i))

    async def execute_pre_middlewares(
        self,
        middlewares_args: Sequence[Any],
        data: dict[str, Any]
    ) -> None:
        for curr_middleware in self:
            gen = await curr_middleware(middlewares_args, data)
            next(gen) if isinstance(gen, Generator) else await anext(gen)
            self.execute_after.appendleft(gen)

    async def execute_post_middlewares(self) -> None:
        while self.execute_after:
            gen = self.execute_after[0]
            try:
                with suppress(StopIteration, StopAsyncIteration):
                    next(gen) if isinstance(gen, Generator) else (await anext(gen))
                self.execute_after.popleft()
            except Exception as e:
                await self.close()
                if not isinstance(e, AbortExecution):
                    raise

    async def close(self) -> None:
        while self.execute_after:
            with suppress(Exception):
                gen = self.execute_after.popleft()
                gen.close() if isinstance(gen, Generator) else await gen.aclose()


class MiddlewareManager(Generic[MiddlewareTypeT], Sequence[CallableWrapper[Any]]):
    def __init__(self) -> None:
        self._middlewares: list[CallableWrapper[Any]] = []

    def register_middleware(self, middleware: MiddlewareTypeT) -> MiddlewareTypeT:
        self._middlewares.append(CallableWrapper(middleware))
        return middleware

    @overload
    def __call__(self, middleware: MiddlewareTypeT, /) -> MiddlewareTypeT: ...

    @overload
    def __call__(self) -> Callable[[MiddlewareTypeT], MiddlewareTypeT]: ...

    def __call__(
        self,
        middleware: MiddlewareTypeT | None = None,
    ) -> MiddlewareTypeT | Callable[[MiddlewareTypeT], MiddlewareTypeT]:
        if middleware is None:
            return self.register_middleware
        return self.register_middleware(middleware)

    @overload
    def __getitem__(self, index: int) -> CallableWrapper[Any]: ...

    @overload
    def __getitem__(self, index: slice) -> list[CallableWrapper[Any]]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> CallableWrapper[Any] | list[CallableWrapper[Any]]:
        return self._middlewares[index]

    def __len__(self) -> int:
        return len(self._middlewares)

    def __bool__(self) -> bool:
        return bool(len(self._middlewares))
