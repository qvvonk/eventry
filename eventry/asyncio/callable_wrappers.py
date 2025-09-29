from __future__ import annotations


__all__ = [
    'CallableWrapper',
    'HandlerMeta',
    'Handler',
]


import inspect
from collections import OrderedDict, deque

from typing_extensions import TYPE_CHECKING, Any, Type, Union, Generic, TypeVar
from dataclasses import dataclass
from collections.abc import Callable, Sequence, Awaitable
from copy import copy

from eventry.config import FromData


if TYPE_CHECKING:
    from .event import Event
    from .filter import Filter
    from .handler_manager import HandlerManager
    from .middleware_manager import MiddlewareWrappedCallable


HandlerManagerTypeT = TypeVar(
    'HandlerManagerTypeT',
    default='HandlerManager',
    bound='HandlerManager',
)

ReturnTypeT = TypeVar('ReturnTypeT', default=Any)


class CallableWrapper(Generic[ReturnTypeT]):
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
        self._callable = __obj
        self._sig = inspect.signature(__obj)
        self._var_args_name = None
        self._var_kwargs_name = None

        for n, p in self._sig.parameters.items():
            if p.kind == inspect.Parameter.VAR_POSITIONAL:
                self._var_args_name = n
            elif p.kind == inspect.Parameter.VAR_KEYWORD:
                self._var_kwargs_name = n

        self._is_async = (
            inspect.iscoroutinefunction(__obj) or
            inspect.iscoroutinefunction(getattr(__obj, '__call__', None))
        )

        self._last_args: Sequence[Any] = ()
        self._last_bound_args: OrderedDict[str, Any] = OrderedDict()

    async def __call__(
        self,
        args: Sequence[Any] = (),
        data: dict[str, Any] | None = None,
    ) -> ReturnTypeT:
        data = data if data is not None else {}
        args = tuple(i if not isinstance(i, FromData) else data[i] for i in args)

        if args == self._last_args:
            bound_args = copy(self._last_bound_args)
            bound = inspect.BoundArguments(self._sig, bound_args)
        else:
            self._last_args = args
            bound = self._sig.bind_partial(*args)
            self._last_bound_args = copy(bound.arguments)

        extra_kwargs: dict[str, Any] = {}
        extra_values: list[Any] = []


        for k, v in data.items():
            if k in bound.arguments:
                continue

            if k == self.varargs_name or k == self.varkw_name:
                continue

            if k in self._sig.parameters:
                bound.arguments[k] = v
            else:
                if self.has_varkw:
                    extra_kwargs[k] = v
                elif self.has_varargs:
                    extra_values.append(v)

        if self.varargs_name and extra_values:
            current_args = list(bound.arguments.get(self.varargs_name, ()))
            current_args.extend(extra_values)
            bound.arguments[self.varargs_name] = current_args

        if self.is_async:
            return await self._callable(*bound.args, **bound.kwargs, **extra_kwargs)  # type: ignore
        return self._callable(*bound.args, **bound.kwargs, **extra_kwargs)  # type: ignore

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
        return self._var_kwargs_name is not None

    @property
    def has_varargs(self) -> bool:
        """
        Returns True if the wrapped callable has a *args parameter.
        """
        return self._var_args_name is not None

    @property
    def varkw_name(self) -> str | None:
        """
        Returns the name of the **kwargs parameter if present, else None.
        """
        return self._var_kwargs_name

    @property
    def varargs_name(self) -> str | None:
        """
        Returns the name of the *args parameter if present, else None.
        """
        return self._var_args_name


class MiddlewareCallable(CallableWrapper[ReturnTypeT]):
    def __init__(
        self,
        __obj: Callable[..., Union[Awaitable[ReturnTypeT], ReturnTypeT]],
        /,
        inheritable: bool = False
    ) -> None:
        super().__init__(__obj)
        self._inheritable = inheritable

    @property
    def inheritable(self) -> bool:
        return self._inheritable


@dataclass(frozen=True)
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

    def wrap_with_middlewares(self) -> MiddlewareWrappedCallable[ReturnTypeT]:
        """
        Build a middleware-wrapped callable for this handler.

        The returned object executes the original handler wrapped into all
        relevant middleware layers.
        """
        from .middleware_manager import MiddlewareManagerTypes, MiddlewareWrappedCallable

        middlewares: deque[CallableWrapper[Any]] = deque()
        middlewares.extendleft(reversed(self.middlewares))

        inner = bool(self.manager.middleware_manager(MiddlewareManagerTypes.INNER_PER_HANDLER))
        inner_inh = bool(self.manager.middleware_manager(MiddlewareManagerTypes.OUTER_PER_HANDLER))

        if inner:
            middlewares.extendleft(
                reversed(self.manager.middleware_manager(MiddlewareManagerTypes.INNER_PER_HANDLER))
            )

        if inner_inh:
            for router in self.manager.router.chain_to_root_router:
                manager = router[self.manager.id]

                middlewares.extendleft(
                    reversed(manager.middleware_manager(MiddlewareManagerTypes.OUTER_PER_HANDLER))
                )

        return MiddlewareWrappedCallable(
            self._callable,
            middlewares=middlewares,
        )
