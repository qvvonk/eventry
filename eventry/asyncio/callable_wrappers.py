from __future__ import annotations


__all__ = [
    'CallableWrapper',
]


import asyncio
import inspect
from typing import TYPE_CHECKING, Any, TypeVar, Generic
from collections.abc import Callable, Awaitable, Sequence


CallableReturnType = TypeVar('CallableReturnType', bound=Any)


class CallableWrapper(Generic[CallableReturnType]):
    def __init__(self, _callable: Callable[..., CallableReturnType]):
        self._callable = _callable
        self._specs = inspect.getfullargspec(_callable)
        self._is_awaitable = (
            inspect.isawaitable(_callable)
            or inspect.iscoroutinefunction(_callable)
            or inspect.iscoroutinefunction(getattr(_callable, '__call__', None))
        )

        self._params_names = tuple(self._specs.args)
        self._kwargs_names = tuple(self._specs.kwonlyargs)
        self._total_names = self._params_names + self._kwargs_names

    async def __call__(
        self,
        positional_only_args: Sequence[Any],
        kwargs: dict[str, Any]
    ) -> CallableReturnType:
        exclude = set()
        if positional_only_args:
            exclude.update(self._params_names[:len(positional_only_args)])

        if not self.has_varkw or exclude:
            kwargs = {
                k: v for k, v in kwargs.items()
                if (not self.has_varkw and k in self._kwargs_names) or
                   (exclude and k not in exclude)
            }

        if self.is_awaitable:
            return await self.callable(*positional_only_args, **kwargs)
        return await asyncio.to_thread(self.callable, *positional_only_args, **kwargs)

    @property
    def callable(self) -> Callable[..., CallableReturnType]:
        """
        The original callable object.
        """
        return self._callable

    @property
    def is_awaitable(self) -> bool:
        """
        Indicates whether the original callable is awaitable.
        """
        return self._is_awaitable

    @property
    def has_varkw(self) -> bool:
        """
        Indicates whether the callable accepts arbitrary keyword arguments via ``**kwargs``.
        """
        return self._specs.varkw is not None

    @property
    def has_varargs(self) -> bool:
        """
        Indicates whether the callable accepts arbitrary arguments via ``*args``.
        """
        return self._specs.varargs is not None

    @property
    def params_names(self) -> tuple[str, ...]:
        """
        Tuple of positional arguments that can be accepted by the original callable.
        """
        return self._params_names

    @property
    def kwargs_names(self) -> tuple[str, ...]:
        """
        Tuple of keyword only arguments that can be accepted by the original callable.
        """
        return self._kwargs_names

    @property
    def total_names(self) -> tuple[str, ...]:
        """
        Tuple of params and keyword params that can be accepted by the original callable.
        """
        return self._total_names