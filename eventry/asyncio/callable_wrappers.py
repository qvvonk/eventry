from __future__ import annotations
__all__ = [
    'CallableWrapper',
    'FromData',
]


from typing import Generic, TypeVar, TYPE_CHECKING, Any
from collections.abc import Callable, Awaitable, Sequence
from types import MethodType, FunctionType
import inspect


if TYPE_CHECKING:
    from eventry.asyncio.filter import Filter
    from eventry.asyncio.handler_manager.base import EventFilter
    from eventry.event import Event


ReturnTypeT = TypeVar('ReturnTypeT')


class FromData(str): ...


class CallableWrapper(Generic[ReturnTypeT]):
    def __init__(
        self,
        __obj: Callable[..., Awaitable[ReturnTypeT]] | Callable[..., ReturnTypeT],
        /,
        *,
        init_method: bool = False,
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
        self._class: type | None = None
        self._init_wrapper: CallableWrapper[None] | None = None
        self._init_method: bool = init_method

        if isinstance(__obj, type):
            if not hasattr(__obj, '__call__'):
                raise TypeError('Class based handlers must implement `__call__` method.')

            _callable = __obj.__call__
            self._class = __obj
            if hasattr(__obj, '__init__') and isinstance(__obj.__init__, FunctionType):
                self._init_wrapper = CallableWrapper(__obj.__init__, init_method=True)

        for i in range(2):
            if isinstance(_callable, (FunctionType, MethodType)):
                break
            if not callable(_callable):
                raise TypeError(f'Expected callable, got {type(__obj).__name__}')
            _callable = getattr(_callable, '__call__')
        else:
            raise TypeError(f'Unable to find __call__ method in {type(__obj).__name__}.')

        self._callable = _callable
        self._has_self = self.is_class or self._init_method or hasattr(self._callable, '__self__')
        _callable = _callable if isinstance(_callable, FunctionType) else _callable.__func__

        # Total amount of non-kwonly args, excluding `self` (if callable is a method),
        # *varargs and **varkwargs
        self._argcount = _callable.__code__.co_argcount - self._has_self

        # Amount of kwonly args, excluding **varkwargs
        self._kwonlyargcount = _callable.__code__.co_kwonlyargcount

        # Total amount of all args, excluding `self` (if callable is a method),
        # excluding *varargs, **varkwargs
        self._total_argcount = self._argcount + self._kwonlyargcount

        self._has_varargs = bool(_callable.__code__.co_flags & inspect.CO_VARARGS)
        self._has_varkw = bool(_callable.__code__.co_flags & inspect.CO_VARKEYWORDS)

        # Amount of non-default positional and keyword args.

        self._non_default_args_count = self._argcount - len(_callable.__defaults__ or ())

        # Amount of non-default kwonly args.
        self._non_default_kwargs_count = self._kwonlyargcount - len(_callable.__kwdefaults__ or {})

        # Total list of all arg names, excluding `self` (if callable is a method),
        # *varargs and **varkwargs
        self._arg_names = _callable.__code__.co_varnames[
            self._has_self : self._argcount + self._kwonlyargcount + 1
        ]

        self._kwargs_defaults = _callable.__kwdefaults__ or {}

        self._is_async = bool(_callable.__code__.co_flags & 0x80)

    def collect_args(
        self,
        args: Sequence[Any] = (),
        data: dict[str, Any] | None = None,
    ) -> tuple[list[Any], dict[str, Any]]:
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
                if name in data:
                    kwargs[name] = data[name]
                    continue

                if name in self._kwargs_defaults:
                    kwargs[name] = self._kwargs_defaults[name]
                    continue

                raise ValueError(
                    f'Cannot find value in provided data dict '
                    f'for non-default kw-only argument {name!r}.',
                )
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

        return pos_args, kwargs

    async def __call__(
        self,
        args: Sequence[Any] = (),
        data: dict[str, Any] | None = None,
    ) -> ReturnTypeT:
        if self._init_method:
            raise TypeError('Cannot call __init__ method directly.')

        _callable = self._callable
        if self._class is not None:
            if self._init_wrapper is not None:
                pos_args, kwargs = self._init_wrapper.collect_args(args, data)
            else:
                pos_args, kwargs = [], {}
            instance = self._class(*pos_args, **kwargs)
            _callable = instance.__call__

        pos_args, kwargs = self.collect_args(args, data)
        if self._is_async:
            return await _callable(*pos_args, **kwargs)
        return _callable(*pos_args, **kwargs)

    @property
    def is_class(self) -> bool:
        return self._class is not None


class Handler(CallableWrapper[ReturnTypeT], Generic[ReturnTypeT]):
    def __init__(
        self,
        __obj: Callable[..., Awaitable[ReturnTypeT]] | Callable[..., ReturnTypeT],
        /,
        handler_id: str,
        event_filter: EventFilter | None,
        filter: Filter | None,
        as_task: bool,
    ):
        from eventry.asyncio.filter import dummy_filter

        super().__init__(__obj)
        self._handler_id = handler_id
        self._as_task = as_task
        self._filter = filter if filter is not None else dummy_filter()
        self._event_filter = event_filter

    @property
    def filter(self) -> Filter:
        return self._filter

    @property
    def as_task(self) -> bool:
        return self._as_task

    @property
    def id(self) -> str:
        return self._handler_id

    @property
    def event_filter(self) -> EventFilter | None:
        return self._event_filter

    def check_event(self, event: Event) -> bool:
        if self.event_filter is None:
            return True
        elif isinstance(self.event_filter, str):
            return self.event_filter == event.name

        return self.event_filter(event)
