from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    ('modules', 'names'),
    [
        pytest.param(
            ['eventry.asyncio', 'eventry.asyncio.router'],
            ['Router', 'DefaultRouter', 'RouterConfig'],
            id='router',
        ),
        pytest.param(
            ['eventry.asyncio', 'eventry.asyncio.dispatcher'],
            ['Dispatcher', 'DispatchingConfig'],
            id='dispatcher',
        ),
        pytest.param(
            ['eventry.asyncio', 'eventry.asyncio.handler_manager'],
            ['HandlerManager', 'DefaultHandlerManager', 'HandlerManagerConfig'],
            id='handler_manager',
        ),
        pytest.param(
            ['eventry.asyncio', 'eventry.asyncio.middleware'],
            ['MiddlewareStorage', 'MiddlewareManager', 'MiddlewareType'],
            id='middleware',
        ),
        pytest.param(
            ['eventry.asyncio', 'eventry.asyncio.filter'],
            [
                'Filter',
                'AndFilter',
                'OrFilter',
                'NotFilter',
                'FilterFromFunction',
                'any_of',
                'all_of',
                'not_',
            ],
            id='filter',
        ),
        pytest.param(
            ['eventry.asyncio', 'eventry.asyncio.config'],
            [
                'Context',
                'FromContext',
                'DispatchingConfig',
                'RouterConfig',
                'HandlerManagerConfig',
                'default_error_callback',
                'default_handler_callback',
            ],
            id='config',
        ),
        pytest.param(
            ['eventry.asyncio', 'eventry.asyncio.dispatching_context'],
            [
                'DispatchingContext',
                'HandlerArgumentSlots',
                'ManagerArgumentSlots',
                'RouterArgumentSlots',
                'ArgumentSlots',
            ],
            id='dispatching_context',
        ),
        pytest.param(
            ['eventry.asyncio', 'eventry.asyncio.event'],
            ['Event', 'ExtendedEvent'],
            id='event',
        ),
        pytest.param(
            ['eventry.asyncio.exceptions'],
            [
                'EventryError',
                'RouterError',
                'RouterAttachmentError',
                'RouterAlreadyAttachedError',
                'DuplicateSubrouterNameError',
                'RouterLoopError',
            ],
            id='exceptions',
        ),
    ],
)
def test_public_imports(modules: list[str], names: list[str]) -> None:
    module_objs = [importlib.import_module(i) for i in modules]

    for name in names:
        objects = []

        for module_name, module in zip(modules, module_objs):
            assert hasattr(module, name), f'`{module_name}` does not have attribute `{name}`.'

            assert hasattr(module, '__all__'), (
                f'`{module_name}` does not have attribute `__all__`.'
            )

            assert name in getattr(module, '__all__'), (
                f'`{module_name}.__all__` does not contain `{name}`.'
            )

            objects.append(getattr(module, name))

        for i in objects:
            assert i is objects[0]
