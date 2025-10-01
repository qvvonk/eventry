from __future__ import annotations

from typing import Any

import pytest

from eventry.asyncio.filter import Filter, not_, all_of, any_of


@pytest.mark.parametrize(
    'filter_fixture,filter_result,dict_updated',
    [
        ['custom_true_filter', True, True],
        ['custom_false_filter', False, False],
    ],
)
@pytest.mark.asyncio
async def test_custom_filter(
    filter_fixture: str,
    filter_result: bool,
    dict_updated: bool,
    event_context: dict[str, Any],
    request: pytest.FixtureRequest,
) -> None:
    f = request.getfixturevalue(filter_fixture)
    result = await f.execute((), event_context)
    assert bool(result) == filter_result
    assert bool('some_data' in event_context) == dict_updated


@pytest.mark.parametrize(
    'filter_fixture,filter_result,dict_updated',
    [
        ['true_filter', True, True],
        ['false_filter', False, False],
    ],
)
@pytest.mark.asyncio
async def test_filter_from_function(
    filter_fixture: str,
    filter_result: bool,
    dict_updated: bool,
    event_context: dict[str, Any],
    request: pytest.FixtureRequest,
) -> None:
    f = request.getfixturevalue(filter_fixture)
    result = await f.execute((), event_context)
    assert bool(result) == filter_result
    assert bool('some_data' in event_context) == dict_updated


@pytest.mark.parametrize(
    'filter_fixture,filter_result,dict_updated',
    [
        ['true_filter', False, True],
        ['false_filter', True, False],
    ],
)
@pytest.mark.asyncio
async def test_invert_filter(
    filter_fixture: str,
    filter_result: bool,
    dict_updated: bool,
    event_context: dict[str, Any],
    request: pytest.FixtureRequest,
) -> None:
    f = ~(request.getfixturevalue(filter_fixture))
    result = await f.execute((), event_context)
    assert bool(result) == filter_result
    assert bool('some_data' in event_context) == dict_updated


@pytest.mark.parametrize(
    'filter_fixture,filter_result,dict_updated',
    [
        ['true_filter', False, True],
        ['false_filter', True, False],
        ['true_filter_function', False, True],
        ['false_filter_function', True, False],
    ],
)
@pytest.mark.asyncio
async def test_not_filter(
    filter_fixture: str,
    filter_result: bool,
    dict_updated: bool,
    event_context: dict[str, Any],
    request: pytest.FixtureRequest,
) -> None:
    f = not_(request.getfixturevalue(filter_fixture))
    result = await f.execute((), event_context)
    assert bool(result) == filter_result
    assert bool('some_data' in event_context) == dict_updated


@pytest.mark.parametrize(
    'filter_fixtures,filter_result,dict_updated',
    [
        (['true_filter', 'true_filter'], True, True),
        (['false_filter', 'false_filter'], False, False),
        (['true_filter', 'false_filter'], True, True),
        (['true_filter', 'true_filter_function'], True, True),
        (['false_filter', 'false_filter_function'], False, False),
        (['true_filter', 'false_filter_function'], True, True),
    ],
)
@pytest.mark.asyncio
async def test_or_filter(
    filter_fixtures: list[str],
    filter_result: bool,
    dict_updated: bool,
    event_context: dict[str, Any],
    request: pytest.FixtureRequest,
) -> None:
    filter_objs: list[Filter] = [request.getfixturevalue(i) for i in filter_fixtures]
    f = filter_objs[0] | filter_objs[1]
    result = await f.execute((), event_context)
    assert bool(result) == filter_result
    assert bool('some_data' in event_context) == dict_updated


@pytest.mark.parametrize(
    'filter_fixtures,filter_result,dict_updated',
    [
        (['true_filter', 'true_filter'], True, True),
        (['false_filter', 'false_filter'], False, False),
        (['true_filter', 'false_filter'], True, True),
        (['true_filter', 'true_filter_function'], True, True),
        (['false_filter', 'false_filter_function'], False, False),
        (['true_filter', 'false_filter_function'], True, True),
    ],
)
@pytest.mark.asyncio
async def test_any_of_filter(
    filter_fixtures: list[str],
    filter_result: bool,
    dict_updated: bool,
    event_context: dict[str, Any],
    request: pytest.FixtureRequest,
) -> None:
    filter_objs: list[Filter] = [request.getfixturevalue(i) for i in filter_fixtures]
    f = any_of(*filter_objs)
    result = await f.execute((), event_context)
    assert bool(result) == filter_result
    assert bool('some_data' in event_context) == dict_updated


@pytest.mark.parametrize(
    'filter_fixtures,filter_result,dict_updated',
    [
        (['true_filter', 'true_filter'], True, True),
        (['false_filter', 'false_filter'], False, False),
        (['true_filter', 'false_filter'], False, True),
        (['true_filter', 'true_filter_function'], True, True),
        (['false_filter', 'false_filter_function'], False, False),
        (['true_filter', 'false_filter_function'], False, True),
    ],
)
@pytest.mark.asyncio
async def test_and_filter(
    filter_fixtures: list[str],
    filter_result: bool,
    dict_updated: bool,
    event_context: dict[str, Any],
    request: pytest.FixtureRequest,
) -> None:
    filter_objs: list[Filter] = [request.getfixturevalue(i) for i in filter_fixtures]
    f = filter_objs[0] & filter_objs[1]
    result = await f.execute((), event_context)
    assert bool(result) == filter_result
    assert bool('some_data' in event_context) == dict_updated


@pytest.mark.parametrize(
    'filter_fixtures,filter_result,dict_updated',
    [
        (['true_filter', 'true_filter'], True, True),
        (['false_filter', 'false_filter'], False, False),
        (['true_filter', 'false_filter'], False, True),
        (['true_filter', 'true_filter_function'], True, True),
        (['false_filter', 'false_filter_function'], False, False),
        (['true_filter', 'false_filter_function'], False, True),
    ],
)
@pytest.mark.asyncio
async def test_all_of_filter(
    filter_fixtures: list[str],
    filter_result: bool,
    dict_updated: bool,
    event_context: dict[str, Any],
    request: pytest.FixtureRequest,
) -> None:
    filter_objs: list[Filter] = [request.getfixturevalue(i) for i in filter_fixtures]
    f = all_of(*filter_objs)
    result = await f.execute((), event_context)
    assert bool(result) == filter_result
    assert bool('some_data' in event_context) == dict_updated
