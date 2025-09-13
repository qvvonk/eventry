from typing import TypeVar, TYPE_CHECKING, Union, Any, Protocol, TypeAlias
from collections.abc import Callable, Awaitable, Coroutine

if TYPE_CHECKING:
    from eventry.asyncio.filter import Filter, LogicalFilter
    from eventry.asyncio.router import Router


FilterTypeT = TypeVar('FilterTypeT', bound=Union[
    Callable[..., bool | Awaitable[bool]],
    'Filter',
    'LogicalFilter'
    ]
)

RouterType = TypeVar('RouterType', bound='Router')
# HandlerType = TypeVar('HandlerType', bound=Callable[..., Any])


class HandlerProtocol(Protocol):
    def __call__(self, *__args: Any, **__kwargs: Any) -> Any: pass


class AsyncHandlerProtocol(Protocol):
    async def __call__(self, *__args: Any, **__kwargs: Any) -> Any: pass


HandlerType: TypeAlias = HandlerProtocol | AsyncHandlerProtocol
FilterType: TypeAlias = Union['Filter', Callable[..., bool | Awaitable[bool]]]
