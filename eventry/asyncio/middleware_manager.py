__all__ = [
    'MiddlewareManager',
    'wrap_with_middlewares',
    'MiddlewareRegistrar',
]


from .callable_wrappers import MiddlewareCallable, CallableWrapper
from collections.abc import Sequence, Iterator, Callable
from typing import Any, TypeVar, overload, Protocol, Generic, Literal
from enum import Enum


WrappedT = TypeVar('WrappedT', bound='Callable[..., Any]')


def wrap_with_middlewares(
    callable_to_wrap: Callable[..., Any] | CallableWrapper[Any],
    middlewares: Sequence[Callable[..., Any] | MiddlewareCallable[Any]],
    wrapper_factory: Callable[[WrappedT, WrappedT | None], WrappedT]
) -> WrappedT:
    current_call = wrapper_factory(callable_to_wrap, None)
    for middleware in reversed(middlewares):
        current_call = wrapper_factory(middleware, current_call)
    return current_call


T = TypeVar('T')


class MiddlewareManagerType(Enum):
    ROUTER_OUTER = 'router.outer'
    ROUTER_INNER = 'router.inner'
    MANAGER_OUTER = 'manager.outer'
    MANAGER_INNER = 'manager.inner'
    HANDLER_OUTER = 'handler.outer'
    HANDLER_INNER = 'handler.inner'


class MiddlewareManager(Sequence[MiddlewareCallable[Any]]):
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

    wrap_with_middlewares = staticmethod(wrap_with_middlewares)


class RegistrarParent(Protocol):
    _middleware_managers: dict[MiddlewareManagerType, MiddlewareManager]


A = TypeVar('A')
B = TypeVar('B')


class MiddlewareRegistrar(Generic[A]):
    def __init__(
        self,
        parent: RegistrarParent,
        allowed_mdw_types: list[MiddlewareManagerType]
    ) -> None:
        self._parent = parent
        self._allowed_mdw_types = allowed_mdw_types

    def __call__(self, scope: A) -> Callable[[B], B]:
        try:
            scope = MiddlewareManagerType(scope)
        except ValueError:
            raise ValueError(f'Invalid middleware scope: {scope}')

        if scope not in self._parent._middleware_managers:
            raise ValueError(f'Middleware manager for {scope} is not registered.')

        manager = self._parent._middleware_managers[scope]

        def register_middleware(middleware: B) -> B:
            manager.register_middleware(middleware)
            return middleware
        return register_middleware
