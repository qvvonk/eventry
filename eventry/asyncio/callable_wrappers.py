from __future__ import annotations


__all__ = [
    'CallableWrapper',
    'MiddlewareCallable',
    'HandlerMeta',
    'Handler',
]


import inspect
from dataclasses import dataclass
from collections import deque
from collections.abc import Callable, Sequence, Awaitable

from typing_extensions import TYPE_CHECKING, Any, Type, Union, Generic, TypeVar
from types import FunctionType, MethodType

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
        '_posonlyargcount',
        '_kwonlyargcount',
        '_non_default_args_count',
        '_non_default_kwargs_count',
        '_total_argcount',
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
        _callable = __obj
        while not isinstance(_callable, (FunctionType, MethodType)):
            if not callable(_callable):
                raise TypeError(f'Expected callable, got {type(__obj).__name__}')
            _callable = getattr(_callable, '__call__')

        self._callable = _callable
        self._is_method = hasattr(self._callable, '__self__')

        # Total amount of non-kwonly args, excluding `self`, (if callable is a method),
        # *varargs and **varkwargs
        self._argcount = self._callable.__code__.co_argcount
        if self._argcount and self._is_method:
            self._argcount -= 1

        # Amount of positional-only args, excluding `self` (if callable is a method),
        # *varargs and **varkwargs
        self._posonlyargcount = self._callable.__code__.co_posonlyargcount
        if self._posonlyargcount and self._is_method:
            self._posonlyargcount -= 1

        # Amount of kwonly args, excluding **varkwargs
        self._kwonlyargcount = self._callable.__code__.co_kwonlyargcount

        # Total amount of all args, excluding `self` (if callable is a method),
        # excluding *varargs, **varkwargs
        self._total_argcount = self._argcount + self._kwonlyargcount

        self._has_varargs = bool(self._callable.__code__.co_flags & inspect.CO_VARARGS)
        self._has_varkw = bool(self._callable.__code__.co_flags & inspect.CO_VARKEYWORDS)

        # Amount of non-default positional args.
        if not self._callable.__defaults__:
            self._non_default_args_count = self._argcount
        else:
            self._non_default_args_count = self._argcount - len(self._callable.__defaults__)

        # Amount of non-default kwonly args.
        if not self._callable.__kwdefaults__:
            self._non_default_kwargs_count = self._kwonlyargcount
        else:
            self._non_default_kwargs_count = self._kwonlyargcount - len(self._callable.__kwdefaults__)

        # Total list of all arg names, excluding `self` (if callable is a method),
        # *varargs and **varkwargs
        self._arg_names = self._callable.__code__.co_varnames[
            self._is_method:self._argcount + self._kwonlyargcount
        ]

        self._is_async = bool(self._callable.__code__.co_flags & 0x80)

    async def __call__(
        self,
        args: Sequence[Any] = (),
        data: dict[str, Any] | None = None,
    ) -> ReturnTypeT:
        if len(args) > self._argcount and not self._has_varargs:
            raise ValueError(f'Too many ({len(args)}) positional arguments. Max: {self._argcount}.')

        if data is None:
            data = {}

        pos_args = [i if type(i) is not FromData else data[i] for i in args] if args else []

        # if there is no *varargs and too many args passed - an exception should be already raised
        # if len(passed args) > len(not-kw-only-args) => excessive passed args will go to *varargs
        bound_pos_args_count = len(pos_args) if len(pos_args) <= self._argcount else self._argcount

        # We are still before the "kw-only args area".
        if bound_pos_args_count < self._non_default_args_count:
            for arg_name_index in range(bound_pos_args_count, self._non_default_args_count):
                name = self._arg_names[arg_name_index]
                if name not in data:
                    raise ValueError(f'Cannot find value in provided data dict '
                                     f'for non-default positional argument {name!r}.')
                pos_args.append(data[name])
                bound_pos_args_count += 1
        # At this state all non-default positional args are bound.

        # Binding non-default kw-only args
        kwargs = {}
        if self._non_default_kwargs_count:
            for arg_name_index in range(self._argcount, self._total_argcount):
                name = self._arg_names[arg_name_index]
                if name not in data:
                    raise ValueError(f'Cannot find value in provided data dict '
                                     f'for non-default kw-only argument {name!r}.')
                kwargs[name] = data[name]
        # At this state all non-default kw-only args are bound.
        # We need to find value overrides for positional and kw-only args with existing
        # default values.

        if self._has_varkw: # passing all names except bound positional args to **kwargs
            bound_pos_arg_names = set(self._arg_names[:bound_pos_args_count])
            kwargs.update({k: v for k, v in data.items() if k not in bound_pos_arg_names})

        # passing only unbound arg names with default values (positional and kw-only) to **kwargs
        else:
            names_to_bind = set(
                *self._arg_names[bound_pos_args_count:self._argcount],
                *self._arg_names[self._argcount+self._non_default_kwargs_count:]
            )
            kwargs.update({k: data[k] for k in names_to_bind if k in data})

        if self._is_async:
            return await self._callable(*pos_args, **kwargs)  # type: ignore
        return self._callable(*pos_args, **kwargs)  # type: ignore


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
