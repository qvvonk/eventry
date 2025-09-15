from __future__ import annotations
from eventry.asyncio.callable_wrappers import CallableWrapper
from collections.abc import Generator, AsyncGenerator, Sequence
from collections import deque
from dataclasses import dataclass, field
from contextlib import suppress
from typing import Any, Generic


class AbortExecution(Exception): ...


class HandlerNotExecuted(Exception): ...


class WrappedWithMiddlewaresCallable:
    def __init__(
        self,
        __callable: CallableWrapper[Any],
        /,
        middlewares: Sequence[
            CallableWrapper[Generator[Any, None, Any] | AsyncGenerator[Any, None]]
        ],
    ):
        self._callable = __callable
        self._middlewares = middlewares

    async def __call__(
        self,
        callable_positional_only_args: Sequence[Any],
        middlewares_positional_only_args: Sequence[Any],
        data,
        state: MiddlewaresExecutionState | None = None,
        execute_after_part: bool = True,
    ):
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
            await self.execute_after_part(state)
        return result

    @staticmethod
    async def execute_after_part(state: MiddlewaresExecutionState):
        while state.execute_after:
            gen = state.execute_after.popleft()
            with suppress(StopIteration, StopAsyncIteration):
                try:
                    next(gen) if isinstance(gen, Generator) else (await gen.__anext__())
                except AbortExecution:
                    return


@dataclass
class MiddlewaresExecutionState:
    middlewares: list[CallableWrapper[Generator[Any, Any, Any] | AsyncGenerator[Any, Any, Any]]]
    _middleware_index: int = field(init=False, repr=False, default=0)
    _execute_after: deque[Generator[Any, None, Any] | AsyncGenerator[Any, None]] = field(
        init=False,
        repr=False,
        default_factory=deque
    )

    def __iter__(self):
        return self

    def __next__(self):
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
