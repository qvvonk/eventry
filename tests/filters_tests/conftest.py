from __future__ import annotations

from typing import Any
from collections.abc import Callable

import pytest

from eventry.asyncio.filter import Filter, FilterFromFunction


@pytest.fixture(scope='module')
def true_filter_function() -> Callable[[], dict[str, Any]]:
    return lambda: {'some_data': True}


@pytest.fixture(scope='module')
def false_filter_function() -> Callable[[], bool]:
    return lambda: False


@pytest.fixture(scope='module')
def custom_true_filter() -> Filter:
    class MyFilter(Filter):
        async def __call__(self) -> dict[str, Any]:
            return {'some_data': True}

    return MyFilter()


@pytest.fixture(scope='module')
def custom_false_filter() -> Filter:
    class MyFilter(Filter):
        async def __call__(self) -> bool:
            return False

    return MyFilter()


@pytest.fixture(scope='module')
def true_filter(true_filter_function: Callable[[], bool]) -> FilterFromFunction:
    return FilterFromFunction(true_filter_function)


@pytest.fixture(scope='module')
def false_filter(false_filter_function: Callable[[], bool]) -> FilterFromFunction:
    return FilterFromFunction(false_filter_function)


@pytest.fixture(scope='function')
def event_context() -> dict[str, Any]:
    return {}
