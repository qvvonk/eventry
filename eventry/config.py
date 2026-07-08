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

    manager_outer_mdw_positional_args: Sequence[Any] = field(default_factory=list)
    manager_inner_mdw_positional_args: Sequence[Any] = field(default_factory=list)

    handler_outer_mdw_positional_args: Sequence[Any] = field(default_factory=list)
    handler_inner_mdw_positional_args: Sequence[Any] = field(default_factory=list)

    filter_positional_args: Sequence[Any] = field(default_factory=list)
    exclude_from_filter_call: set[str] = field(default_factory=set)