from __future__ import annotations
__all__ = [
    'CallableWrapper',
    'FromData',
    'Handler',
    'MiddlewareCallable',
]

import asyncio
from typing import Generic, TypeVar, TYPE_CHECKING, Any
from collections.abc import Callable, Awaitable, Sequence, Mapping
from types import MethodType, FunctionType
from functools import partial
import inspect


if TYPE_CHECKING:
    from eventry.asyncio.filter import Filter
    from eventry.asyncio.handler_manager.base import EventFilter
    from eventry.event import Event


ReturnTypeT = TypeVar('ReturnTypeT')
R = TypeVar('R')
T = TypeVar('T')
RT = TypeVar('RT')


class FromData(str): ...


class CallableWrapper(Generic[ReturnTypeT]):
    def __init__(
        self,
        __obj: Callable[..., Awaitable[ReturnTypeT]] | Callable[..., ReturnTypeT],
        /,
    ) -> None:
        if isinstance(__obj, partial):
            self._partial_args = list(__obj.args or [])
            self._partial_kwargs = __obj.keywords or {}
            _callable = __obj.func
        else:
            self._partial_args = []
            self._partial_kwargs = {}
            _callable = __obj

        for i in range(2):
            if isinstance(_callable, (FunctionType, MethodType)):
                break
            if not callable(_callable):
                raise TypeError(f'Expected callable, got {type(__obj).__name__}')
            _callable = getattr(_callable, '__call__')
        else:
            raise TypeError(f'Unable to find __call__ method in {type(__obj).__name__}.')


        self._callable = _callable
        self._has_self = hasattr(_callable, '__self__')
        _callable = _callable if isinstance(self._callable, FunctionType) else _callable.__func__
        _code = _callable.__code__
        self._posonly_c = _code.co_posonlyargcount - self._has_self
        self._args_c = _code.co_argcount - self._has_self
        self._kwonly_c = _code.co_kwonlyargcount
        self._total_args_c = self._args_c + self._kwonly_c

        self._has_varargs = bool(_code.co_flags & inspect.CO_VARARGS)
        self._has_varkw = bool(_code.co_flags & inspect.CO_VARKEYWORDS)

        self._nondef_args_c = self._args_c - len(_callable.__defaults__ or ())
        self._nondef_kwonly_c = self._kwonly_c - len(_callable.__kwdefaults__ or {})
        self._names = _code.co_varnames[self._has_self : self._args_c + self._kwonly_c + self._has_self]
        self._defaults = _callable.__defaults__ or ()
        self._kwargs_defaults = getattr(_callable, '__kwdefaults__', {})
        self._is_async = bool(_code.co_flags & 0x80)

    def collect_args(self, args: Sequence[Any] = (), kwargs: Mapping[str, Any] | None = None) -> tuple[list[Any], dict[str, Any]]:
        args = self._partial_args + list(args)
        kwargs = self._partial_kwargs | dict(kwargs or {})

        if len(args) > self._args_c and not self._has_varargs:
            raise ValueError(
                f'Too many positional arguments. '
                f'Callable {self._callable.__qualname__!r} has no varargs '
                f'and accepts at most {self._args_c} positional arguments, '
                f'but {len(args)} were given.\n'
                f'Passed args: {args}.'
            )

        r_args = [i if type(i) is not FromData else kwargs[i] for i in args] if args else []

        bound_args_c = len(r_args) if len(r_args) <= self._args_c else self._args_c
        if bound_args_c < self._nondef_args_c:
            for arg_name_index in range(bound_args_c, self._nondef_args_c):
                name = self._names[arg_name_index]
                if name not in kwargs:
                    raise ValueError(
                        f'Callable {self._callable.__qualname__!r} '
                        f'accepts {self._nondef_args_c} non-default arguments, '
                        f'but only {len(args)} positional args were given.\n'
                        f'Considering this, tried to find value for non-default argument '
                        f'{arg_name_index} ({name!r}) in given kwargs dict, but no value was found.'
                    )
                r_args.append(kwargs[name])
                bound_args_c += 1

        if bound_args_c < self._posonly_c:
            for name_index in range(bound_args_c, self._posonly_c):
                name = self._names[name_index]
                if name in kwargs:
                    r_args.append(kwargs[name])
                else:
                    r_args.append(self._defaults[name_index - self._nondef_args_c])
                bound_args_c += 1

        r_kwargs = {}
        if self._nondef_kwonly_c:
            for arg_name_index in range(self._args_c, self._total_args_c):
                name = self._names[arg_name_index]
                if name in kwargs:
                    r_kwargs[name] = kwargs[name]
                    continue

                if name in self._kwargs_defaults:
                    continue

                raise ValueError(
                    f'No value was found in given kwargs dict for non-default '
                    f'kw-only argument {name!r}.'
                )

        if self._has_varkw:
            bound_pos_arg_names = set(self._names[:bound_args_c])
            r_kwargs.update({k: v for k, v in kwargs.items() if k not in bound_pos_arg_names})
        else:
            for name_index in range(bound_args_c, self._args_c):
                name = self._names[name_index]
                if name in kwargs:
                    r_kwargs[name] = kwargs[name]
            for name_index in range(self._args_c + self._nondef_kwonly_c, self._total_args_c):
                name = self._names[name_index]
                if name in kwargs:
                    r_kwargs[name] = kwargs[name]

        return r_args, r_kwargs

    def __call__(
        self,
        args: Sequence[Any] = (),
        data: dict[str, Any] | None = None,
        to_thread: bool = True
    ) -> Awaitable[ReturnTypeT]:
        pos_args, kwargs = self.collect_args(args, data)
        if self._is_async:
            return self._callable(*pos_args, **kwargs)
        if to_thread:
            return asyncio.to_thread(self._callable, *pos_args, **kwargs)
        return self._blocking_async_call(self._callable, pos_args, kwargs)

    async def _blocking_async_call(
        self,
        _call: Callable[..., R],
        args: Sequence[Any],
        kwargs: Mapping[str, Any]
    ) -> R:
        return _call(*args, **kwargs)


class MiddlewareCallable(CallableWrapper[ReturnTypeT]):
    def __init__(
        self,
        __obj: Callable[..., Awaitable[ReturnTypeT]] | Callable[..., ReturnTypeT],
        /,
    ) -> None:
        super().__init__(__obj)


class Handler(CallableWrapper[ReturnTypeT], Generic[ReturnTypeT]):
    def __init__(
        self,
        __obj: Callable[..., Awaitable[ReturnTypeT]] | Callable[..., ReturnTypeT],
        /,
        *,
        handler_id: str,
        event_filter: EventFilter | None,
        filter: Filter | None = None,
        as_task: bool = False,
        outer_middlewares: Sequence[MiddlewareCallable[Any] | Callable[..., Any]] | None = None,
        inner_middlewares: Sequence[MiddlewareCallable[Any] | Callable[..., Any]] | None = None,
    ):
        from eventry.asyncio.filter import dummy_filter
        outer_middlewares = outer_middlewares or []
        inner_middlewares = inner_middlewares or []

        super().__init__(__obj)
        self._handler_id = handler_id
        self._as_task = as_task
        self._filter = filter if filter is not None else dummy_filter()
        self._event_filter = event_filter
        self._outer_middlewares = [
            MiddlewareCallable(i) for i in outer_middlewares if not isinstance(i, MiddlewareCallable)
        ]
        self._inner_middlewares = [
            MiddlewareCallable(i) for i in inner_middlewares if not isinstance(i, MiddlewareCallable)
        ]

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

    @property
    def outer_middlewares(self) -> list[MiddlewareCallable[Any]]:
        return self._outer_middlewares

    @property
    def inner_middlewares(self) -> list[MiddlewareCallable[Any]]:
        return self._inner_middlewares

    def check_event(self, event: Event) -> bool:
        if self.event_filter is None:
            return True
        elif isinstance(self.event_filter, str):
            return self.event_filter == event.name

        return self.event_filter(event)
