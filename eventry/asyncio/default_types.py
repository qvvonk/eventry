from typing import TypeVar, TYPE_CHECKING, Union
from collections.abc import Callable, Awaitable

if TYPE_CHECKING:
    from eventry.asyncio.filter import Filter
    from eventry.asyncio.router import Router


FilterType = TypeVar('FilterType', bound=Union[
    Callable[..., bool | Awaitable[bool]],
    'Filter'
    ]
)

RouterType = TypeVar('RouterType', bound='Router')
