from collections.abc import Callable, Awaitable
from typing import Generic, TypeVar, Type, Any, Union, ParamSpec


Params = ParamSpec('Params')
ReturnType = TypeVar('ReturnType', bound=Any)


class SomeClass(Generic[Params, ReturnType]):
    def __init__(self, callable: Callable[Params, Union[Awaitable[ReturnType], ReturnType]]) -> None:
        self._callable = callable

    @property
    def callable(self) -> Callable[Params, Union[Awaitable[ReturnType], ReturnType]]:
        return self._callable



def my_callable(some: str, another: int, some_another: bool) -> None:
    ...


instance: SomeClass[[str, int], None] = SomeClass(my_callable)