from .base import HandlerManager
from typing import Generic, TypeVar, Any
from collections.abc import Callable
from ..filter import Filter


HandlerType = TypeVar('HandlerType', bound=Callable[..., Any])
FilterType = TypeVar('FilterType', bound=Filter)


class DefaultHandlerManager(HandlerManager[FilterType, HandlerType], Generic[FilterType, HandlerType]):
    ...
