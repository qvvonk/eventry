from __future__ import annotations


__all__ = [
    'MiddlewareStorage',
    'MiddlewareManager',
    'MiddlewareType',
    'MdwsType',
]


from typing import Any, Literal, TypeVar, overload
from enum import Enum
from collections.abc import Callable, Iterator, Sequence, Awaitable

from .callable_wrappers import CallableWrapper, MiddlewareCallable


class MiddlewareType(Enum):
    ROUTER_OUTER = 'router.outer'
    ROUTER_INNER = 'router.inner'
    MANAGER_OUTER = 'manager.outer'
    MANAGER_INNER = 'manager.inner'
    HANDLER_OUTER = 'handler.outer'
    HANDLER_INNER = 'handler.inner'


MdwsType = Literal[
    'router.outer',
    'router.inner',
    'manager.outer',
    'manager.inner',
    'handler.outer',
    'handler.inner',
    MiddlewareType.ROUTER_OUTER,
    MiddlewareType.ROUTER_INNER,
    MiddlewareType.MANAGER_OUTER,
    MiddlewareType.MANAGER_INNER,
    MiddlewareType.HANDLER_OUTER,
    MiddlewareType.HANDLER_INNER,
]


WrappedT = TypeVar('WrappedT', bound='Callable[..., Any]')

T = TypeVar('T')


class MiddlewareStorage(Sequence[MiddlewareCallable[Any]]):
    def __init__(self) -> None:
        self._middlewares: list[MiddlewareCallable[Any]] = []

    def register_middleware(self, middleware: T) -> T:
        m = MiddlewareCallable(middleware)
        self._middlewares.append(m)
        return middleware

    @overload
    def __call__(self, func: T, /) -> T:
        pass

    @overload
    def __call__(self) -> Callable[[T], T]:
        pass

    @overload
    def __call__(self, func: T, /) -> T:
        pass

    def __call__(self, func: T | None = None, /) -> T | Callable[[T], T]:
        def inner(middleware: T) -> T:
            self.register_middleware(middleware)
            return middleware

        if func is None:
            return inner
        return inner(func)

    @overload
    def __getitem__(self, index: int) -> MiddlewareCallable[Any]: ...

    @overload
    def __getitem__(self, index: slice) -> list[MiddlewareCallable[Any]]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> MiddlewareCallable[Any] | list[MiddlewareCallable[Any]]:
        return self._middlewares[index]

    def __len__(self) -> int:
        return len(self._middlewares)

    def __bool__(self) -> bool:
        return bool(len(self._middlewares))

    def __reversed__(self) -> Iterator[MiddlewareCallable]:
        return reversed(self._middlewares)

    @staticmethod
    def wrap_with_middlewares(
        callable_to_wrap: Callable[..., Any] | CallableWrapper[Any],
        middlewares: Sequence[Callable[..., Any] | MiddlewareCallable[Any]],
        wrapper_factory: Callable[[WrappedT, WrappedT | None], WrappedT],
    ) -> WrappedT:
        current_call = wrapper_factory(callable_to_wrap, None)
        for middleware in reversed(middlewares):
            current_call = wrapper_factory(middleware, current_call)
        return current_call


class MiddlewareManager:
    def __init__(self, allowed_types: Sequence[MdwsType]) -> None:
        self._allowed_types = set(MiddlewareType(i) for i in allowed_types)
        self._storages: dict[MiddlewareType, MiddlewareStorage] = {}

    def get_middlewares_storage(self, type: MdwsType) -> MiddlewareStorage | None:
        try:
            mdw_type = MiddlewareType(type)
        except ValueError:
            return None
        return self._storages.get(mdw_type)

    def set_middlewares_storage(self, type: MdwsType, storage: MiddlewareStorage | None) -> None:
        if storage is not None and not isinstance(storage, MiddlewareStorage):
            raise TypeError(
                f'Middlewares storage must be an instance of `MiddlewareStorage`, '
                f'not {storage.__class__.__name__!r}.',
            )

        try:
            type = MiddlewareType(type)
        except ValueError:
            raise ValueError(f'Invalid middleware manager type: {type!r}.') from None

        if type not in self._allowed_types:
            raise ValueError(
                f'This middleware manager does not accept middleware storages of type {type!r}.',
            )

        if storage is not None:
            self._storages[type] = storage
        else:
            self._storages.pop(type, None)

    def __call__(self, *, scope: MdwsType) -> Callable[[T], T]:
        storage = self.get_middlewares_storage(scope)
        if storage is None:
            raise ValueError(
                f'This manager does not contain middleware storage for {scope!r} scope.'
            ) from None
        return storage.__call__()


_CALLABLE = Callable[[dict[str, Any]], Awaitable[Any]]


def _make_mdw_wrapper_factory(
    args_call: Callable[[dict[str, Any]], list[Any]] | None = None,
    next_call_arg_name: str = 'next_call',
) -> Callable[[_CALLABLE, _CALLABLE | None], _CALLABLE]:
    def wrapper_factory(to_wrap: _CALLABLE, prev_wrapped: _CALLABLE | None) -> _CALLABLE:
        async def wrapped(context: dict[str, Any]) -> Any:
            if prev_wrapped is None:
                return await to_wrap(context)

            context.update({next_call_arg_name: prev_wrapped})
            call = to_wrap if isinstance(to_wrap, CallableWrapper) else CallableWrapper(to_wrap)
            return await call(args_call(context) if args_call is not None else [], context)

        return wrapped

    return wrapper_factory
