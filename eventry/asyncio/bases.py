from __future__ import annotations


__all__ = [
    'CallableInfo',
    'HandlerInfo',
    'HandlerMeta',
    'HandlerCallableType',
    'MiddlewareCallableType',
    'WrappedWithMiddlewaresType',
]


import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Type
from dataclasses import field, dataclass
from collections.abc import Callable, Awaitable


if TYPE_CHECKING:
    from eventry.asyncio.handler_manager import HandlerManager

    from ..event import Event


HandlerCallableType = Callable[..., Any]
"""
Represents the type of handler callables.

Primarily used in ``HandlerManager`` decorators to ensure type checkers recognize
that decorated functions are not modified or wrapped, but simply registered and
returned unchanged.
"""

MiddlewareCallableType = Callable[..., Any]
WrappedWithMiddlewaresType = Callable[..., Awaitable[Any]]
# todo: middleware type


@dataclass
class CallableInfo:
    """
    Represents information about a callable.
    """

    callable: Callable[..., Any]
    """
    The callable object this info refers to.
    """

    is_awaitable: bool = field(init=False)
    """
    Indicates whether the callable is awaitable.
    """

    has_double_star_kwargs: bool = field(init=False)
    """
    Indicates whether the callable accepts ``**kwargs`` (or any other ``**`` variables).
    """

    param_names: set[str] = field(init=False)
    """
    Set of params and keyword params that accepted by ``CallableInfo.callable``.
    """

    def __post_init__(self) -> None:
        func = self.callable
        specs = inspect.getfullargspec(func)

        self.is_awaitable = (
            inspect.isawaitable(func)
            or inspect.iscoroutinefunction(func)
            or inspect.iscoroutinefunction(getattr(func, '__call__', None))
        )
        self.has_double_star_kwargs = specs.varkw is not None
        self.param_names = set(specs.args + specs.kwonlyargs)

    async def __call__(self, **workflow_data: Any) -> Any:
        if not self.has_double_star_kwargs:
            workflow_data = {k: v for k, v in workflow_data.items() if k in self.param_names}

        if self.is_awaitable:
            return await self.callable(**workflow_data)
        return await asyncio.to_thread(self.callable, **workflow_data)


@dataclass(frozen=True)
class HandlerMeta:
    definition_filename: str | None
    definition_lineno: int
    registration_filename: str
    registration_lineno: int

    @classmethod
    def from_callable(
        cls,
        callable: Callable[..., Any],
        registration_frame: inspect.FrameInfo,
    ) -> HandlerMeta:
        is_class_based = not (
            inspect.isfunction(callable) or inspect.ismethod(callable) or inspect.isclass(callable)
        )

        h = callable.__class__ if is_class_based else callable

        return HandlerMeta(
            definition_filename=inspect.getsourcefile(h),
            definition_lineno=inspect.getsourcelines(h)[1],
            registration_filename=registration_frame.filename,
            registration_lineno=registration_frame.lineno,
        )


@dataclass
class HandlerInfo(CallableInfo):
    name: str
    """Handler name."""

    event_type_filter: Type[Event[Any]] | None
    """Event type on which this handler should be executed."""

    filter: CallableInfo | None
    """Handler filter."""

    manager: HandlerManager[Any]
    """Handler manager to which this handler is bound."""

    meta: HandlerMeta
    """Handler meta."""

    as_task: bool = False
    """Whether to run handler as task or not."""

    middlewares: list[MiddlewareCallableType] = field(default_factory=list)
    """List of middlewares."""

    ensure_after: dict[str, Any] = field(default_factory=dict)

    def can_be_executed(self, executed_handlers: dict[str, Any]) -> bool:
        if not self.ensure_after:
            return True

        for i in self.ensure_after:
            if i not in executed_handlers:
                return False

            if self.ensure_after[i] is Ellipsis:
                continue

            result = executed_handlers[i]

            if result != self.ensure_after[i]:
                return False
        else:
            return True
