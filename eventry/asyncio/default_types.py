from __future__ import annotations

from typing import TYPE_CHECKING, Any, Union, TypeAlias
from collections.abc import Callable, Awaitable


if TYPE_CHECKING:
    from eventry.asyncio.filter import Filter


HandlerType: TypeAlias = Callable[..., Any]
FilterType: TypeAlias = Union['Filter', Callable[..., bool | Awaitable[bool]]]
MiddlewareType: TypeAlias = Callable[..., Any]
