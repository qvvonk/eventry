from __future__ import annotations


__all__ = [
    'CallableWrapper',
    'MiddlewareCallable',
    'HandlerMeta',
    'Handler',
]


import inspect
from dataclasses import dataclass
from types import MethodType, FunctionType
from collections.abc import Callable, Sequence, Awaitable

from typing_extensions import TYPE_CHECKING, Any, Type, Union, Generic, TypeVar

from eventry.config import FromData

from ..exceptions import _EarlyFinalized


if TYPE_CHECKING:
    from .event import Event
    from .filter import Filter
    from .handler_manager import HandlerManager


HandlerManagerTypeT = TypeVar(
    'HandlerManagerTypeT',
    default='HandlerManager[Any, Any, Any, Any]',
    bound='HandlerManager[Any, Any, Any, Any]',
)

ReturnTypeT = TypeVar('ReturnTypeT', default=Any)


class CallableWrapper(Generic[ReturnTypeT]):
    __slots__ = (
        '_is_method',
        '_callable',
        '_argcount',
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

        .. warning::
            Callable wrapper doesn't work with `functools.partial` objects, and callables
            implemented in C.

        Usage:
            >>> import asyncio
            >>> def my_function(arg1, arg2, arg3='some', **kwargs):
            >>>     print(arg1, arg2, arg3, kwargs)
            >>> wrapper = CallableWrapper(my_function)
            >>> positional_args = (1, )
            >>> data = {'arg2': 2, 'arg3': 'overwrite', 'another': 'value', 'one': 'more'}
            >>> loop = asyncio.new_event_loop()
            >>> loop.run_until_complete(wrapper(positional_args, data))
            1, 2, 'overwrite', {'another': 'value', 'one': 'more'}

        Behavior of extra data:
          - If the callable has varkw, extra keys from ``data`` go there.
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
            self._non_default_kwargs_count = self._kwonlyargcount - len(
                self._callable.__kwdefaults__,
            )

        # Total list of all arg names, excluding `self` (if callable is a method),
        # *varargs and **varkwargs
        self._arg_names = self._callable.__code__.co_varnames[
            self._is_method : self._argcount + self._kwonlyargcount + 1
        ]

        self._is_async = bool(self._callable.__code__.co_flags & 0x80)

    async def __call__(
        self,
        args: Sequence[Any] = (),
        data: dict[str, Any] | None = None,
    ) -> ReturnTypeT:
        if len(args) > self._argcount and not self._has_varargs:
            raise ValueError(
                f'Too many ({len(args)}) positional arguments. Max: {self._argcount}.',
            )

        if data is None:
            data = {}

        pos_args = [i if type(i) is not FromData else data[i] for i in args] if args else []

        # if there is no *varargs and too many args passed - an exception should be already raised
        # if len(passed args) > len(positional args) => excessive passed args will go to *varargs
        #
        # Example:
        # def function(a, b, c, d, *args): ...
        # Passed args: (1, 2, 3, 4, 5, 6) (`5` and `6` goes to `*args`).
        bound_pos_arg_names_count = (
            len(pos_args) if len(pos_args) <= self._argcount else self._argcount
        )

        # We are still before the "kw-only args area".
        # If there are some unbound non-default non-kwonly (positional) args,
        # we need to locate their values in data dict.
        #
        # Example:
        # def function(a, b, c, d): ...
        # Passed args: (1, 2, 3) (`d` has no value).
        if bound_pos_arg_names_count < self._non_default_args_count:
            for arg_name_index in range(bound_pos_arg_names_count, self._non_default_args_count):
                name = self._arg_names[arg_name_index]
                if name not in data:
                    raise ValueError(
                        f'Cannot find value in provided data dict '
                        f'for non-default positional argument {name!r}.',
                    )
                pos_args.append(data[name])
                bound_pos_arg_names_count += 1
        # At this state all non-default non-kwonly (positional) args are bound.
        # Example:
        # def function(a, b, c, d): ...
        # Passed args: (1, 2, 3) => (a=1, b=2, c=3)
        # Passed data dict: {'d': 4, 'another': 5} => d=4

        # Binding non-default kw-only args if they exist.
        kwargs = {}
        if self._non_default_kwargs_count:
            # From the last positional arg name (exclusive) to the last arg name,
            # i.e., kw-only args.
            for arg_name_index in range(self._argcount, self._total_argcount):
                name = self._arg_names[arg_name_index]
                if name not in data:
                    raise ValueError(
                        f'Cannot find value in provided data dict '
                        f'for non-default kw-only argument {name!r}.',
                    )
                kwargs[name] = data[name]
        # At this state all non-default kw-only args are bound.
        # We need to find value overrides for positional and kw-only args with existing
        # default values.

        if self._has_varkw:  # passing all names except bound positional args to **kwargs
            bound_pos_arg_names = set(self._arg_names[:bound_pos_arg_names_count])
            kwargs.update({k: v for k, v in data.items() if k not in bound_pos_arg_names})

        # passing only unbound arg names with default values (positional and kw-only) to **kwargs
        else:
            for name_index in range(bound_pos_arg_names_count, self._argcount):
                name = self._arg_names[name_index]
                if name in data:
                    kwargs[name] = data[name]
            for name_index in range(
                self._argcount + self._non_default_kwargs_count,
                self._total_argcount,
            ):
                name = self._arg_names[name_index]
                if name in data:
                    kwargs[name] = data[name]

        if self._is_async:
            return await self._callable(*pos_args, **kwargs)  # type: ignore
        return self._callable(*pos_args, **kwargs)  # type: ignore


class MiddlewareCallable(CallableWrapper[ReturnTypeT]):
    __slots__ = ('_inheritable',)

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
    ) -> None:
        """
        Executes current handler wrapped with filter and outer-inner-handler middlewares.

        If an exception occurred while executing the filter or handler, finalizes all middlewares
        and returns `None`.

        If there is an unhandled exception after middlewares are finalized, raises it.

        :return None: If an exception occurred during the executing process and it *was handled*
        by middleware finalizers.

        :raises FinalizingError: If an exception occurred during the executing process,
         and it was *not handled* in middleware finalizers. The original exception will be stored in
         `FinalizingError.__cause__`.
        """
        from eventry.asyncio.middleware_manager import (
            MiddlewaresExecutor,
            MiddlewareManagerTypes,
            MiddlewareWrappedCallable,
        )

        data = data if data is not None else {}

        outer_middlewares = self.manager.collect_middlewares(
            MiddlewareManagerTypes.OUTER_PER_HANDLER,
        )
        inner_middlewares = self.manager.collect_middlewares(
            MiddlewareManagerTypes.INNER_PER_HANDLER,
        )
        inner_middlewares.extend(self.middlewares)

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
        except _EarlyFinalized:
            return
        # except FinalizingError: raise
        # No other exceptions are expected here.

        if not r:
            # Only FinalizingError can be raised here.
            await executor.finalize_middlewares()
            return

        wrapped_handler = MiddlewareWrappedCallable(self._callable, inner_middlewares)

        try:
            await wrapped_handler(
                callable_args=self.manager._config.handler_positional_only_args,
                middlewares_args=self.manager._config.middleware_positional_only_args,
                data=data,
                executor=executor,
            )
        except _EarlyFinalized:
            return
        # except FinalizingError: raise
        # No other exceptions are expected here.
