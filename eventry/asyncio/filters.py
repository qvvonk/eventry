from __future__ import annotations


__all__ = [
    'Filter',
    'CallableFilter',
    'AwaitableFilter',
    'any_of',
    'all_of',
    'not_',
]


from typing import Any, Callable, Iterable, Awaitable
from abc import ABC, abstractmethod

from .bases import CallableInfo


CallableFilter = Callable[..., bool]
AwaitableFilter = Callable[..., Awaitable[bool]]


class Filter(ABC):
    """
    Abstract base class for all filters.

    All custom class-based filters must inherit from this class and implement the asynchronous
    ``__call__`` method, which defines the filtering logic.

    Supports logical composition using the following operators:
        - ``&`` (AND) creates an ``AndFilter``
        - ``|`` (OR) creates an ``OrFilter``
        - ``~`` (NOT) creates a ``NotFilter``
    """

    @abstractmethod
    async def __call__(self, *args: Any, **kwargs: Any) -> bool: ...

    def __and__(self, other: Filter | CallableFilter | AwaitableFilter) -> AndFilter:
        """
        Combines this filter with another using logical AND.

        Returns a new ``AndFilter`` that succeeds only if both filters return ``True``.
        """

        if not isinstance(other, Filter):
            other = _convert_filters([other])[0]
        return AndFilter(self, other)

    def __or__(self, other: Filter | CallableFilter | AwaitableFilter) -> OrFilter:
        """
        Combines this filter with another using logical OR.

        Returns a new ``OrFilter`` that succeeds if at least one filter returns ``True``.
        """

        if not isinstance(other, Filter):
            other = _convert_filters([other])[0]
        return OrFilter(self, other)

    def __invert__(self) -> NotFilter:
        """
        Inverts the result of this filter.

        Returns a new ``NotFilter`` that returns ``True`` when this filter returns False,
        and vice versa.
        """

        return NotFilter(self)


class AndFilter(Filter):
    """
    Composite filter that succeeds only if all wrapped filters succeed.

    Typically, created using the ``&`` operator or ``all_of()`` function.
    """

    def __init__(self, *filters: Filter) -> None:
        self._filters = [CallableInfo(i) for i in filters]

    async def __call__(self, **workflow_data: Any) -> bool:
        for i in self._filters:
            if not await i(**workflow_data):
                return False
        return True


class OrFilter(Filter):
    """
    Composite filter that succeeds if at least one wrapped filter succeeds.

    Typically, created using the ``|`` operator or ``any_of()`` function.
    """

    def __init__(self, *filters: Filter) -> None:
        self._filters = [CallableInfo(i) for i in filters]

    async def __call__(self, **workflow_data: Any) -> bool:
        for i in self._filters:
            if await i(**workflow_data):
                return True
        return False


class NotFilter(Filter):
    """
    Inverted filter that negates the result of another filter.

    Typically, created using the ``~`` operator.
    """

    def __init__(self, filter: Filter) -> None:
        self._filter = CallableInfo(filter)

    async def __call__(self, **workflow_data: Any) -> bool:
        return not (await self._filter(**workflow_data))


class FilterFromFunction(Filter):
    """
    Wrapper that turns a regular function (sync or async) into a ``Filter``.

    Used internally to adapt user-defined callables into the filter system.
    """

    def __init__(self, function: CallableFilter | AwaitableFilter) -> None:
        self._function = CallableInfo(function)

    async def __call__(self, **workflow_data: Any) -> bool:
        return bool(await self._function(**workflow_data))


def _convert_filters(
    filters: Iterable[CallableFilter | AwaitableFilter | Filter],
) -> list[Filter]:
    """
    Converts all function filters to ``FilterFromFunction`` objects.

    :param filters: iterable of filters to convert.
    :return: list of converted filters.
    """
    converted_filters: list[Filter] = []
    for i in filters:
        if isinstance(i, Filter):
            converted_filters.append(i)
        else:
            converted_filters.append(FilterFromFunction(i))

    return converted_filters


def any_of(*filters: CallableFilter | AwaitableFilter | Filter) -> OrFilter:
    """
    Creates a composite filter that returns ``True``
    if at least one of the given filters returns ``True``.

    This function behaves like the built-in ``any()`` function,
    but returns a new ``OrFilter`` instance that can be used as a filter object.

    Each passed filter may be:
    - an instance of ``Filter``,
    - a synchronous function returning ``bool``,
    - or an asynchronous function returning ``bool``.

    If no filters are provided, the resulting filter always returns ``False``.
    """
    return OrFilter(*_convert_filters(filters))


def all_of(*filters: CallableFilter | AwaitableFilter | Filter) -> AndFilter:
    """
    Creates a composite filter that returns ``True`` only if all the given filters return ``True``.

    This function behaves like the built-in ``all()`` function,
    but returns a new ``AndFilter`` instance that can be used as a filter object.

    Each passed filter may be:
    - an instance of ``Filter``,
    - a synchronous function returning ``bool``,
    - or an asynchronous function returning ``bool``.

    If no filters are provided, the resulting filter always returns ``True``.
    """
    return AndFilter(*_convert_filters(filters))


def not_(filter: CallableFilter | AwaitableFilter | Filter) -> NotFilter:
    """
    Creates a filter that negates the given filter.

    This function behaves like the built-in ``not`` operator,
    but returns a new ``NotFilter`` instance that can be used as a filter object.

    The passed filter may be:
    - an instance of ``Filter``,
    - a synchronous function returning ``bool``,
    - or an asynchronous function returning ``bool``.
    """
    return NotFilter(_convert_filters([filter])[0])
