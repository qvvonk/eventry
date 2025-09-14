from __future__ import annotations


__all__ = [
    'Filter',
    'CallableFilter',
    'LogicalFilter',
    'any_of',
    'all_of',
    'not_',
]


from typing import Any, Callable, Iterable, Awaitable, TypeAlias
from abc import ABC
from collections.abc import Sequence

from .callable_wrappers import CallableWrapper


CallableFilter: TypeAlias = Callable[..., bool | Awaitable[bool]]


class Filter:
    """
    Abstract base class for all filters.

    All custom class-based filters must inherit from this class and implement the asynchronous
    ``__call__`` method, which defines the filtering logic.

    Supports logical composition using the following operators:
        - ``&`` (AND) creates an ``AndFilter``
        - ``|`` (OR) creates an ``OrFilter``
        - ``~`` (NOT) creates a ``NotFilter``
    """

    def __init__(self) -> None:
        self._call_id = id(self.__call__)
        self._call_wrapper: CallableWrapper[bool] = CallableWrapper(self.__call__)

    async def __call__(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def __and__(self, other: CallableFilter | Filter) -> AndFilter:
        """
        Combines this filter with another using logical AND.

        Returns a new ``AndFilter`` that succeeds only if both filters return ``True``.
        """

        if not isinstance(other, Filter):
            other = convert_filters([other])[0]
        return AndFilter(self, other)

    def __or__(self, other: CallableFilter | Filter) -> OrFilter:
        """
        Combines this filter with another using logical OR.

        Returns a new ``OrFilter`` that succeeds if at least one filter returns ``True``.
        """

        if not isinstance(other, Filter):
            other = convert_filters([other])[0]
        return OrFilter(self, other)

    def __invert__(self) -> NotFilter:
        """
        Inverts the result of this filter.

        Returns a new ``NotFilter`` that returns ``True`` when this filter returns False,
        and vice versa.
        """

        return NotFilter(self)

    async def execute(self, args: Sequence[Any], data: dict[str, Any]) -> bool:
        if id(self.__call__) != self._call_id:
            self._call_id = id(self.__call__)
            self._call_wrapper = CallableWrapper(self.__call__)

        return await self._call_wrapper(args, data)


class LogicalFilter(Filter, ABC): ...


class AndFilter(LogicalFilter):
    """
    Composite filter that succeeds only if all wrapped filters succeed.

    Typically, created using the ``&`` operator or ``all_of()`` function.
    """

    def __init__(self, *filters: CallableFilter | Filter) -> None:
        super().__init__()
        self._filters: list[Filter] = [
            i if isinstance(i, Filter) else FilterFromFunction(i) for i in filters
        ]

    async def execute(self, args: Sequence[Any], data: dict[str, Any]) -> bool:
        for i in self._filters:
            if not (await i.execute(args, data)):
                return False
        return True


class OrFilter(LogicalFilter):
    """
    Composite filter that succeeds if at least one wrapped filter succeeds.

    Typically, created using the ``|`` operator or ``any_of()`` function.
    """

    def __init__(self, *filters: CallableFilter | Filter) -> None:
        super().__init__()
        self._filters: list[Filter] = [
            i if isinstance(i, Filter) else FilterFromFunction(i) for i in filters
        ]

    async def execute(self, args: Sequence[Any], data: dict[str, Any]) -> bool:
        for i in self._filters:
            if await i.execute(args, data):
                return True
        return False


class NotFilter(LogicalFilter):
    """
    Inverted filter that negates the result of another filter.

    Typically, created using the ``~`` operator.
    """

    def __init__(self, filter: CallableFilter | Filter) -> None:
        super().__init__()
        self._filter: Filter = filter if isinstance(filter, Filter) else FilterFromFunction(filter)

    async def execute(self, args: Sequence[Any], data: dict[str, Any]) -> bool:
        return not (await self._filter(args, data))


class FilterFromFunction(LogicalFilter):
    """
    Wrapper that turns a regular function (sync or async) into a ``Filter``.

    Used internally to adapt user-defined callables into the filter system.
    """

    def __init__(self, function: CallableFilter) -> None:
        setattr(self, '__call__', function)
        super().__init__()


def convert_filters(filters: Iterable[CallableFilter | Filter]) -> list[Filter]:
    """
    Converts all function filters to ``FilterFromFunction`` objects.

    :param filters: iterable of filters to convert.
    :return: list of converted filters.
    """
    return [i if isinstance(i, Filter) else FilterFromFunction(i) for i in filters]


def any_of(*__filters: CallableFilter | Filter) -> OrFilter:
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
    return OrFilter(*convert_filters(__filters))


def all_of(*__filters: CallableFilter | Filter) -> AndFilter:
    """
    Creates a composite filter that returns ``True`` only if all the given filters return ``True``.

    This function behaves like the built-in ``all()`` function,
    but returns a new ``AndFilter`` instance that can be used as a filter object.

    Each passed filter may be:
    - an instance of ``Filter``,
    - a synchronous function returning ``bool``,
    - or an asynchronous function returning ``bool``.

    If no filters are provided, the resulting filter always returns ``True``.

    Args:
        /:
    """
    return AndFilter(*convert_filters(__filters))


def not_(__filter: CallableFilter | Filter, /) -> NotFilter:
    """
    Creates a filter that negates the given filter.

    This function behaves like the built-in ``not`` operator,
    but returns a new ``NotFilter`` instance that can be used as a filter object.

    The passed filter may be:
    - an instance of ``Filter``,
    - a synchronous function returning ``bool``,
    - or an asynchronous function returning ``bool``.
    """
    return NotFilter(convert_filters([__filter])[0])
