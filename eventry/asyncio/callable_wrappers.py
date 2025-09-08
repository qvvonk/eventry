from __future__ import annotations


__all__ = [
    'CallableWrapper',
    'HandlerMeta',
    'Handler'
]


import asyncio
import inspect
from typing import TYPE_CHECKING, Any, TypeVar, Generic, ParamSpec
from collections.abc import Callable, Awaitable, Sequence
from dataclasses import dataclass


if TYPE_CHECKING:
    from .handler_manager import HandlerManager
    from .filter import Filter


R = TypeVar('R', bound=Any)
P = ParamSpec('P')


class CallableWrapper(Generic[P, R]):
    def __init__(self, _callable: Callable[P, R], /):
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
    ) -> R:
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
    def callable(self) -> Callable[P, R]:
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


@dataclass(frozen=True)
class HandlerMeta:
    definition_filename: str | None
    definition_lineno: int
    registration_filename: str
    registration_lineno: int

    @classmethod
    def from_callable(
        cls,
        _callable: Callable[..., Any],
        registration_frame: inspect.FrameInfo,
    ) -> HandlerMeta:
        is_user_defined_class_instance = not (
            inspect.isfunction(_callable) or inspect.ismethod(_callable) or inspect.isclass(_callable)
        )

        obj = _callable.__class__ if is_user_defined_class_instance else _callable

        return HandlerMeta(
            definition_filename=inspect.getsourcefile(obj),
            definition_lineno=inspect.getsourcelines(obj)[1],
            registration_filename=registration_frame.filename,
            registration_lineno=registration_frame.lineno,
        )


class Handler(Generic[P, R], CallableWrapper[P, R]):
    def __init__(
        self,
        _callable: Callable[P, R],
        handler_id: str,
        handler_manager: HandlerManager[Any, Any],
        filter: Filter | None,
        as_task: bool,
        meta: HandlerMeta,
    ):
        super().__init__(_callable)
        self._handler_manager = handler_manager
        self._handler_id = handler_id
        self._filter = filter
        self._meta = meta
        self._as_task = as_task

    @property
    def handler_manager(self) -> HandlerManager[Any, Any]:
        return self._handler_manager

    @property
    def filter(self) -> Filter | None:
        return self._filter

    @property
    def meta(self) -> HandlerMeta:
        return self._meta

    @property
    def as_task(self) -> bool:
        return self._as_task

    @property
    def handler_id(self) -> str:
        return self._handler_id
