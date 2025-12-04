from __future__ import annotations


__all__ = [
    'CallableWrapper',
    'MiddlewareCallable',
    'HandlerMeta',
    'Handler',
]


import inspect
from dataclasses import dataclass
from copy import copy
from collections import OrderedDict, deque
from collections.abc import Callable, Sequence, Awaitable

from typing_extensions import TYPE_CHECKING, Any, Type, Union, Generic, TypeVar

from eventry.config import FromData

from ..exceptions import EarlyFinalized


if TYPE_CHECKING:
    from .event import Event
    from .filter import Filter
    from .handler_manager import HandlerManager


HandlerManagerTypeT = TypeVar(
    'HandlerManagerTypeT',
    default='HandlerManager',
    bound='HandlerManager',
)

ReturnTypeT = TypeVar('ReturnTypeT', default=Any)


class CallableWrapper(Generic[ReturnTypeT]):
    __slots__ = (
        '_is_method',
        '_callable',
        '_argcount',
        '_kwonlyargcount',
        '_has_varargs',
        '_has_varkw',
        '_arg_names',
        '_is_async',
    )
    def __init__(
        self,
        __obj: Callable[..., Union[Awaitable[ReturnTypeT], ReturnTypeT]],
        /,
    ) -> None:
        """
        Wrapper around any callable to allow dynamic invocation with positional
        arguments and a data dictionary for named parameters.

        Supports sync and async functions / objects with sync and async `__call__` method with
        any signature.

        Usage:
            >>> def my_function(arg1, arg2, arg3='some', **kwargs):
            >>>     print(arg1, arg2, arg3, kwargs)
            >>> wrapper = CallableWrapper(my_function)
            >>> positional_args = (1, )
            >>> data = {'arg2': 2, 'arg3': 'overwrite', 'another': 'value', 'one': 'more'}
            >>> await wrapper(positional_args, data)
            1, 2, 'overwrite', {'another': 'value', 'one': 'more'}

        Behavior of extra data:
          - If the callable has varkw, extra keys from ``data`` go there.
          - Else, if the callable has varargs but no varkw, extra values from
            ``data`` are appended to it.
          - Otherwise, extra keys are ignored.

        :param __obj: Callable to wrap. Can be a normal function, coroutine
                      function, or object with sync/async __call__.
        """
        self._is_method = not isinstance(__obj, FunctionType)
        self._callable: FunctionType | MethodType = (
            getattr(__obj, '__call__') if self._is_method else __obj
        )

        self._argcount = self._callable.__code__.co_argcount
        self._kwonlyargcount = self._callable.__code__.co_kwonlyargcount

        self._has_varargs = bool(self._callable.__code__.co_flags & inspect.CO_VARARGS)
        self._has_varkw = bool(self._callable.__code__.co_flags & inspect.CO_VARKEYWORDS)

        self._arg_names = self._callable.__code__.co_varnames[
            self._is_method:self._argcount + self._kwonlyargcount + 1
        ]

        self._is_async = inspect.iscoroutinefunction(__obj) or inspect.iscoroutinefunction(
            getattr(__obj, '__call__', None),
        )

    async def __call__(
        self,
        args: Sequence[Any] = (),
        data: dict[str, Any] | None = None,
    ) -> ReturnTypeT:
        data = data if data is not None else {}
        args = tuple(i if type(i) is not FromData else data[i] for i in args)
        bound_names = self._arg_names[: len(args)]
        names_to_bind = self._arg_names[len(args) :]

        if self._has_varkw:
            kwargs = {k: v for k, v in data.items() if k not in bound_names}
        else:
            kwargs = {k: data[k] for k in names_to_bind if k in data}

        if self.is_async:
            return await self._callable(*args, **kwargs)  # type: ignore
        return self._callable(*args, **kwargs)  # type: ignore

    @property
    def is_async(self) -> bool:
        """
        Indicates whether the original callable is awaitable.
        """
        return self._is_async

    @property
    def has_varkw(self) -> bool:
        """
        Returns True if the wrapped callable has a **kwargs parameter.
        """
        return self._has_varkw

    @property
    def has_varargs(self) -> bool:
        """
        Returns True if the wrapped callable has a *args parameter.
        """
        return self._has_varargs


class MiddlewareCallable(CallableWrapper[ReturnTypeT]):
    __slots__ = ('_inheritable', )

    def __init__(
        self,
        __obj: Callable[..., Union[Awaitable[ReturnTypeT], ReturnTypeT]],
        /,
        inheritable: bool = False,
    ) -> None:
        super().__init__(__obj)
        self._inheritable = inheritable

    @property
    def inheritable(self) -> bool:
        return self._inheritable


@dataclass(frozen=True, slots=True)
class HandlerMeta:
    """
    Represents metadata about a handler.
    """

    definition_filename: str | None
    """Name of the file where the handler is defined."""

    definition_lineno: int
    """Line number in the file where the handler is defined."""

    registration_filename: str
    """Name of the file where the handler was added to the handler manager."""

    registration_lineno: int
    """Line number in the file where the handler was added to the handler manager."""

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
    __slots__ = (
        '_handler_manager',
        '_handler_id',
        '_meta',
        '_middlewares',
        '_as_task',
        '_filter',
        '_on_event',
    )

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
        from eventry.asyncio.filter import FilterFromFunction

        super().__init__(__obj)
        self._handler_manager = handler_manager
        self._handler_id = handler_id
        self._meta = meta
        self._middlewares = middlewares
        self._as_task = as_task
        self._filter = filter if filter is not None else FilterFromFunction(lambda *args: True)

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

    async def execute_wrapped(
        self,
        data: dict[str, Any] | None = None,
        inherited_outer_middlewares: deque[MiddlewareCallable[Any]] | None = None,
        inherited_inner_middlewares: deque[MiddlewareCallable[Any]] | None = None,
    ) -> None:
        from eventry.asyncio.middleware_manager import (
            MiddlewaresExecutor,
            MiddlewareManagerTypes,
            MiddlewareWrappedCallable,
        )

        data = data if data is not None else {}

        outer_middlewares = inherited_outer_middlewares or deque()
        inner_middlewares = inherited_inner_middlewares or deque()

        curr_outer = (
            self.manager.middleware_manager(MiddlewareManagerTypes.OUTER_PER_HANDLER) or []
        )
        curr_inner = (
            self.manager.middleware_manager(MiddlewareManagerTypes.INNER_PER_HANDLER) or []
        )

        outer_middlewares = outer_middlewares + deque(curr_outer)
        inner_middlewares = inner_middlewares + deque(curr_inner) + deque(self.middlewares)

        executor = MiddlewaresExecutor()
        wrapped_filter = MiddlewareWrappedCallable(self._filter.execute, outer_middlewares)

        try:
            r = await wrapped_filter(
                callable_args=(
                    self.manager._config.filter_positional_only_args,
                    data,
                ),
                middlewares_args=self.manager._config.middleware_positional_only_args,
                data=data,
                finalize=False,
                executor=executor,
            )
        except EarlyFinalized:
            return

        if not r:
            await executor.finalize_middlewares()
            return

        wrapped_handler = MiddlewareWrappedCallable(self._callable, inner_middlewares)

        try:
            await wrapped_handler(
                self.manager._config.handler_positional_only_args,
                self.manager._config.middleware_positional_only_args,
                data,
                finalize=True,
                executor=executor,
            )
        except EarlyFinalized:
            return

        # todo: hook to handler return
