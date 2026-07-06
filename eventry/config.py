__all__ = [
    'HandlerManagerConfig',
]


from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HandlerManagerConfig:
    handler_positional_args: Sequence[Any] = field(default_factory=list)
    exclude_from_handler_call: set[str] = field(default_factory=set)

    filter_positional_args: Sequence[Any] = field(default_factory=list)
    exclude_from_filter_call: set[str] = field(default_factory=set)