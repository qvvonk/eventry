from __future__ import annotations

from collections.abc import Callable, Awaitable

from typing_extensions import TYPE_CHECKING, Any, Union, TypeAlias


if TYPE_CHECKING:
    from eventry.asyncio.filter import Filter


HandlerType: TypeAlias = Callable[..., Any]
FilterType: TypeAlias = Union['Filter', Callable[..., bool | Awaitable[bool]]]
MiddlewareType: TypeAlias = Callable[..., Any]
