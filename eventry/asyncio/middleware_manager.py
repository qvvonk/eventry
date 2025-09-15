from __future__ import annotations


__all__ = [
    'MiddlewareManager',
    'WrappedWithMiddlewaresCallable',
    'MiddlewaresExecutionState',
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
R = TypeVar('R')


class WrappedWithMiddlewaresCallable(Generic[R]):
    def __init__(
        self,
        __callable: Union[Callable[..., Union[Awaitable[R], R]], CallableWrapper[R]],
        /,
        middlewares: Iterable[CallableWrapper[Any] | Callable[..., Any]],
    ) -> None:
        self._callable = (
            __callable if isinstance(__callable, CallableWrapper) else CallableWrapper(__callable)
        )
        self._middlewares = middlewares

    async def __call__(
        self,
        callable_positional_only_args: Sequence[Any],
        middlewares_positional_only_args: Sequence[Any],
        data: dict[str, Any],
        state: MiddlewaresExecutionState | None = None,
        execute_after_part: bool = True,
    ) -> R:
        state = state or MiddlewaresExecutionState(middlewares=list(self._middlewares))

        for curr_middleware in state:
            try:
                gen = await curr_middleware(middlewares_positional_only_args, data)
                if isinstance(gen, Generator):
                    next(gen)
                    state.execute_after.appendleft(gen)
                elif isinstance(gen, AsyncGenerator):
                    await gen.__anext__()
                    state.execute_after.appendleft(gen)
                # if it is regular function, do not execute after callable
            except AbortExecution:
                raise HandlerNotExecuted

        result = await self._callable(callable_positional_only_args, data)

        if execute_after_part:
            await state.execute_after_part()
        return result


@dataclass
class MiddlewaresExecutionState:
    middlewares: list[CallableWrapper[Any]] = field(default_factory=list)

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

    def __iter__(self) -> MiddlewaresExecutionState:
        return self

    def __next__(self) -> CallableWrapper[Any]:
        try:
            middleware = self.middlewares[self._middleware_index]
        except IndexError:
            raise StopIteration
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

    async def execute_after_part(self) -> None:
        while self.execute_after:
            gen = self.execute_after.popleft()
            with suppress(StopIteration, StopAsyncIteration):
                try:
                    next(gen) if isinstance(gen, Generator) else (await gen.__anext__())
                except AbortExecution:
                    return


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
