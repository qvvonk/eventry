from __future__ import annotations

from typing import final


@final
class FromContext(str):
    def __repr__(self) -> str:
        text = super().__repr__()
        return f'{self.__class__.__name__}({text})'

    def __str__(self) -> str:
        return self.__repr__()


@final
class ContextType:
    def __repr__(self) -> str:
        return self.__class__.__name__

    def __str__(self) -> str:
        return 'Context'


Context = ContextType()
