from __future__ import annotations


__all__ = ['Provider', 'provider', 'is_provider', 'get_provider']


import inspect
from typing import Any, Generic, TypeVar
from collections.abc import Callable, Awaitable, Generator, AsyncIterator, AsyncGenerator


T = TypeVar('T')


class Provider(Generic[T]):
    def __init__(
        self,
        factory: Callable[
            [], T | Awaitable[T] | Generator[T, None, None] | AsyncGenerator[T, None]
        ],
    ):
        self._factory = factory
        self._isgen = inspect.isgeneratorfunction(factory) or inspect.isasyncgenfunction(factory)
        self._isasync = (
            inspect.iscoroutinefunction(factory)
            if not self._isgen
            else inspect.isasyncgenfunction(factory)
        )

    async def __call__(self) -> AsyncIterator[T]:
        result = self._factory()

        if not self._isgen:
            yield (await result) if self._isasync else result
            return

        stop_iter_exc = StopAsyncIteration if self._isasync else StopIteration
        try:
            try:
                value = await anext(result) if self._isasync else result
            except stop_iter_exc:
                raise RuntimeError('Provider generator did not yield a value.') from None

            try:
                yield value
            finally:
                try:
                    await anext(result) if self._isasync else result
                except stop_iter_exc:
                    pass
                else:
                    raise RuntimeError('Provider generator yielded more than one value.')
        finally:
            await result.aclose() if self._isasync else result
        return


def provider(callable: T) -> T:
    setattr(callable, '__eventry_provider__', Provider(callable))
    return callable


def is_provider(obj: Any) -> bool:
    if not callable(obj):
        return False

    if not hasattr(obj, '__eventry_provider__'):
        return False

    if not isinstance(getattr(obj, '__eventry_provider__'), Provider):
        return False

    provider_obj: Provider[Any] = getattr(obj, '__eventry_provider__')
    if provider_obj._factory is not obj:
        return False

    return True


def get_provider(obj: Callable[..., T]) -> Provider[T]:
    if not is_provider(obj):
        raise ValueError('Object is not a provider.')

    return getattr(obj, '__eventry_provider__')
