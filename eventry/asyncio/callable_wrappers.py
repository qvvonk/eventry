from __future__ import annotations


__all__ = [
    'CallableWrapper',
    'HandlerMeta',
    'Handler',
]


import inspect
from typing import TYPE_CHECKING, Any, Type, Union, Generic, TypeVar
from dataclasses import dataclass
from types import MethodType
from collections.abc import Callable, Sequence, Awaitable

from eventry.config import FromData


if TYPE_CHECKING:
    from .event import Event
    from .filter import Filter
    from .handler_manager import HandlerManager


HandlerManagerTypeT = TypeVar(
    'HandlerManagerTypeT',
    default='HandlerManager',
    bound='HandlerManager[Any, Any, Any, Any]',
)

ReturnTypeT = TypeVar('ReturnTypeT')


class CallableWrapper(Generic[ReturnTypeT]):
    def __init__(
        self,
        __obj: Callable[..., Union[Awaitable[ReturnTypeT], ReturnTypeT]],
        /,
    ) -> None:
        self._callable = __obj
        self._specs = inspect.getfullargspec(__obj)
        self._is_async = inspect.iscoroutinefunction(__obj) or inspect.iscoroutinefunction(
            getattr(__obj, '__call__', None),
        )
        self._params_names = (
            tuple(self._specs.args[1:])
            if isinstance(self._callable, MethodType)
            else tuple(self._specs.args)
        )
        self._kwargs_names = tuple(self._specs.kwonlyargs)
        self._total_names = self._params_names + self._kwargs_names

    async def __call__(
        self,
        args: Sequence[Any] = tuple(),
        data: dict[str, Any] | None = None,
    ) -> ReturnTypeT:
        data = data if data is not None else {}
        exclude: set[str] = set()
        if args:
            exclude.update(self._params_names[: len(args)])
            args = [i if not isinstance(i, FromData) else data[i] for i in args]

        if not self.has_varkw or exclude:
            kwargs = {}
            for k, v in data.items():
                if k in exclude:
                    continue
                if not self.has_varkw and k not in self.params_names:
                    continue
                kwargs[k] = v
            data = kwargs

        result = self._callable(*args, **data)
        if inspect.isawaitable(result):
            return await result
        return result

    @property
    def is_async(self) -> bool:
        """
        Indicates whether the original callable is awaitable.
        """
        return self._is_async

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
        return HandlerMeta(
            definition_filename=inspect.getsourcefile(_callable),
            definition_lineno=inspect.getsourcelines(_callable)[1],
            registration_filename=registration_frame.filename,
            registration_lineno=registration_frame.lineno,
        )


class Handler(CallableWrapper[ReturnTypeT], Generic[ReturnTypeT, HandlerManagerTypeT]):
    def __init__(
        self,
        __obj: Callable[..., Union[Awaitable[ReturnTypeT], ReturnTypeT]],
        /,
        handler_id: str,
        handler_manager: HandlerManagerTypeT,
        on_event: Type[Event] | None,
        filter: Union[Filter, None],
        middlewares: list[CallableWrapper[Any]],
        as_task: bool,
        meta: HandlerMeta,
    ):
        super().__init__(__obj)
        self._handler_manager = handler_manager
        self._handler_id = handler_id
        self._filter = filter
        self._meta = meta
        self._middlewares = middlewares
        self._as_task = as_task

        if self._handler_manager.event_type_filter and on_event:
            raise ValueError('')  # todo: err message
        self._on_event = on_event

    @property
    def manager(self) -> HandlerManagerTypeT:
        return self._handler_manager

    @property
    def filter(self) -> Union[Filter, None]:
        return self._filter

    @property
    def meta(self) -> HandlerMeta:
        return self._meta

    @property
    def as_task(self) -> bool:
        return self._as_task

    @property
    def id(self) -> str:
        return self._handler_id

    @property
    def on_event(self) -> Type[Event] | None:
        return self.manager.event_type_filter or self._on_event

    @property
    def middlewares(self) -> list[CallableWrapper[Any]]:
        return self._middlewares
