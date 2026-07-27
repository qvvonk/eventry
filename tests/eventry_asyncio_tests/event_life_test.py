import pytest

from eventry.asyncio import ExtendedEvent, Dispatcher, DefaultRouter


router = DefaultRouter(name='test_router')


@router.outer_middleware()
async def router_outer_middleware(next_call, data, event: ExtendedEvent):
    event['workflow'] = ['router.outer']
    await next_call(data)
    event['workflow'].append('router.outer.end')


@router.inner_middleware()
async def router_inner_middleware(next_call, data, event: ExtendedEvent):
    event['workflow'].append('router.inner')
    await next_call(data)
    event['workflow'].append('router.inner.end')


@router.on_event.manager_outer_middleware()
async def manager_outer_middleware(next_call, data, event: ExtendedEvent):
    event['workflow'].append('manager.outer')
    await next_call(data)
    event['workflow'].append('manager.outer.end')


@router.on_event.manager_inner_middleware()
async def manager_inner_middleware(next_call, data, event: ExtendedEvent):
    event['workflow'].append('manager.inner')
    await next_call(data)
    event['workflow'].append('manager.inner.end')


@router.on_event.handler_outer_middleware()
async def handler_outer_middleware(next_call, data, event: ExtendedEvent):
    event['workflow'].append('handler.outer')
    await next_call(data)
    event['workflow'].append('handler.outer.end')


@router.on_event.handler_inner_middleware()
async def handler_inner_middleware(next_call, data, event: ExtendedEvent):
    event['workflow'].append('handler.inner')
    await next_call(data)
    event['workflow'].append('handler.inner.end')


async def handler_specific_outer_middleware(next_call, data, event: ExtendedEvent):
    event['workflow'].append('handler_specific.outer')
    await next_call(data)
    event['workflow'].append('handler_specific.outer.end')


async def handler_specific_inner_middleware(next_call, data, event: ExtendedEvent):
    event['workflow'].append('handler_specific.inner')
    await next_call(data)
    event['workflow'].append('handler_specific.inner.end')


@router.on_event(
    outer_middlewares=[handler_specific_outer_middleware],
    inner_middlewares=[handler_specific_inner_middleware],
)
async def handler(event: ExtendedEvent):
    event['workflow'].append('handler')


@pytest.mark.asyncio
async def test_event_workflow():
    event = ExtendedEvent()
    dp = Dispatcher(router)
    await dp.propagate_event(event)

    assert event['workflow'] == [
        'router.outer',
        'router.inner',
        #
        'manager.outer',
        'manager.inner',
        #
        'handler.outer',
        'handler_specific.outer',
        'handler.inner',
        'handler_specific.inner',
        #
        'handler',
        #
        'handler_specific.inner.end',
        'handler.inner.end',
        'handler_specific.outer.end',
        'handler.outer.end',
        #
        'manager.inner.end',
        'manager.outer.end',
        #
        'router.inner.end',
        'router.outer.end'
    ]