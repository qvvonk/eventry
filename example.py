from __future__ import annotations

from typing import Generic, TypeVar, ParamSpec
from collections.abc import Callable

from typing_extensions import TypeVarTuple


MustHaveParams = TypeVarTuple('MustHaveParams')
UserDefinedT = ParamSpec('UserDefinedT')
ReturnType = TypeVar('ReturnType')


class SomeClass(Generic[*MustHaveParams, ReturnType]):
    P = ParamSpec('P', bound=MustHaveParams)

    def method(self, func: Callable[P, ReturnType]) -> Callable[P, ReturnType]:
        return func


a: SomeClass[int, str, bool] = SomeClass()


def my_handler(arg1: int) -> bool:
    return True


test = a.method(my_handler)
