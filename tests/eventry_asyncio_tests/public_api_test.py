from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    ('public_module', 'implementation_module', 'names'),
    [
        pytest.param(
            'eventry.asyncio',
            'eventry.asyncio.router',
            ['Router', 'DefaultRouter', 'RouterConfig'],
            id='router',
        ),
        pytest.param(
            'eventry.asyncio',
            'eventry.asyncio.dispatcher',
            ['Dispatcher', 'EventDispatchingConfig'],
            id='dispatcher',
        ),
        pytest.param(
            'eventry.asyncio',
            'eventry.asyncio.handler_manager',
            ['HandlerManager', 'DefaultHandlerManager', 'HandlerManagerConfig'],
            id='handler_manager',
        ),
        pytest.param(
            'eventry.asyncio.filter',
            'eventry.asyncio.filter',
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
            'eventry.asyncio.exceptions',
            'eventry.asyncio.exceptions',
            [
                'EventryError',
                'RouterError',
                'RouterAttachmentError',
                'RouterAlreadyAttachedError',
                'DuplicateSubrouterNameError',
                'RouterLoopError',
            ],
            id='exceptions'
        )
    ],
)
def test_public_imports(
    public_module,
    implementation_module,
    names,
):
    public = importlib.import_module(public_module)
    implementation = importlib.import_module(implementation_module)

    for name in names:
        assert getattr(public, name) is getattr(implementation, name), 'Different objects.'
        assert hasattr(public, '__all__'), 'Public has no `__all__`.'
        assert hasattr(implementation, '__all__'), 'Implementation has no `__all__`.'
        assert name in getattr(public, '__all__'), 'Name not in `public.__all__`.'
        assert name in getattr(implementation, '__all__'), 'Name not in `implementation.__all__`.'
