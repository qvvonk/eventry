from __future__ import annotations

from collections.abc import Callable, Awaitable

import pytest
from typing_extensions import Any, Literal

from eventry.asyncio.callable_wrappers import CallableWrapper


@pytest.fixture(scope='module')
def sync_callable_with_no_args() -> Callable[[], Literal[1]]:
    def function() -> Literal[1]:
        return 1

    return function


@pytest.fixture(scope='module')
def sync_callable_wrapper_with_no_args(
    sync_function_with_no_args: Callable[[], Literal[1]],
) -> CallableWrapper[Literal[1]]:
    return CallableWrapper(sync_function_with_no_args)


@pytest.fixture(scope='module')
def async_callable_with_no_args() -> Callable[[], Awaitable[Literal[1]]]:
    async def function() -> Literal[1]:
        return 1

    return function


@pytest.fixture(scope='module')
def async_callable_wrapper_with_no_args(
    async_callable_with_no_args: Callable[[], Awaitable[Literal[1]]],
) -> CallableWrapper[Literal[1]]:
    return CallableWrapper(async_callable_with_no_args)


@pytest.fixture(scope='module')
def callable_with_varkwargs() -> Callable[..., dict[str, Any]]:
    def function(**kwargs: Any) -> dict[str, Any]:
        return kwargs

    return function


@pytest.fixture(scope='module')
def callable_wrapper_with_varkwargs(
    callable_with_varkwargs: Callable[..., dict[str, Any]],
) -> CallableWrapper[dict[str, Any]]:
    return CallableWrapper(callable_with_varkwargs)


@pytest.fixture(scope='module')
def callable_with_varargs() -> Callable[..., tuple[Any, ...]]:
    def function(*args: Any) -> tuple[Any, ...]:
        return args

    return function


@pytest.fixture(scope='module')
def callable_wrapper_with_varargs(
    callable_with_varargs: Callable[..., tuple[Any, ...]],
) -> CallableWrapper[tuple[Any, ...]]:
    return CallableWrapper(callable_with_varargs)


@pytest.fixture(scope='module')
def callable_with_varkwargs_and_varargs() -> Callable[..., tuple[tuple[Any, ...], dict[str, Any]]]:
    def function(*args: Any, **kwargs: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
        return args, kwargs

    return function


@pytest.fixture(scope='module')
def callable_wrapper_with_varkwargs_and_varargs(
    callable_with_varkwargs_and_varargs: Callable[..., tuple[tuple[Any, ...], dict[str, Any]]],
) -> CallableWrapper[tuple[tuple[Any, ...], dict[str, Any]]]:
    return CallableWrapper(callable_with_varkwargs_and_varargs)


@pytest.fixture(scope='module')
def specific_args_values() -> dict[str, Any]:
    return {
        'arg1': 1,
        'arg2': '2',
        'arg3': False,
    }


@pytest.fixture(scope='module')
def callable_with_specific_args() -> Callable[..., Any]:
    def function(arg1: int, arg2: str, arg3: bool) -> Any:
        return arg1, arg2, arg3

    return function


@pytest.fixture(scope='module')
def callable_wrapper_with_specific_args(
    callable_with_specific_args: Callable[..., Any],
) -> CallableWrapper[Any]:
    return CallableWrapper(callable_with_specific_args)
