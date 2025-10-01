from __future__ import annotations

import pytest
from typing_extensions import Any, Literal

from eventry.asyncio.callable_wrappers import CallableWrapper


class TestCallableWrapper:
    @pytest.mark.asyncio
    async def test_sync_function_with_no_args(
        self,
        async_callable_wrapper_with_no_args: CallableWrapper[Literal[1]],
    ) -> None:
        assert await async_callable_wrapper_with_no_args() == 1

    @pytest.mark.asyncio
    async def test_async_function_with_no_args(
        self,
        async_callable_wrapper_with_no_args: CallableWrapper[Literal[1]],
    ) -> None:
        assert await async_callable_wrapper_with_no_args() == 1

    @pytest.mark.asyncio
    async def test_wrapper_with_varkwargs(
        self,
        callable_wrapper_with_varkwargs: CallableWrapper[dict[str, Any]],
    ) -> None:
        kwargs = {'a': 1, 'b': '2', 'c': True}
        assert await callable_wrapper_with_varkwargs(data=kwargs) == kwargs

    @pytest.mark.asyncio
    async def test_wrapper_with_varargs(
        self,
        callable_wrapper_with_varargs: CallableWrapper[tuple[Any, ...]],
    ) -> None:
        positional_only_args = (1, '2', True)
        assert await callable_wrapper_with_varargs(positional_only_args) == positional_only_args
