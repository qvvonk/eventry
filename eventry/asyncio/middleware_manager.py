__all__ = [
    'MiddlewareManager'
]


from .callable_wrappers import MiddlewareCallable
from collections.abc import Sequence, Iterator, Callable
from typing import Any, TypeVar, overload
from eventry.asyncio.callable_wrappers import InheritableMark


T = TypeVar('T')


class MiddlewareManager(Sequence[MiddlewareCallable[Any]]):
    def __init__(self) -> None:
        self._middlewares: list[MiddlewareCallable[Any]] = []

    def register_middleware(self, middleware: T, inheritable: InheritableMark = False) -> T:
        m = MiddlewareCallable(middleware, inheritable=inheritable)
        self._middlewares.append(m)
        return middleware

    @overload
    def __call__(self, func: T, /) -> T:
        pass

    @overload
    def __call__(
        self,
        /,
        *,
        inheritable: bool = False,
    ) -> Callable[[T], T]:
        pass

    @overload
    def __call__(self, func: T, /, *, inheritable: bool = False) -> T:
        pass

    def __call__(
        self,
        func: T | None = None,
        /,
        *,
        inheritable: InheritableMark = False,
    ) -> T | Callable[[T], T]:
        def inner(middleware: T) -> T:
            self.register_middleware(middleware, inheritable=inheritable)
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
