__all__ = [
    'HandlerManagerConfig',
]


from collections.abc import Sequence, Callable, Awaitable
from dataclasses import dataclass, field
from typing import Any


@dataclass(kw_only=True)
class HandlerManagerConfig:
    handler_positional_args: Sequence[Any] = field(default_factory=list)

    manager_outer_mdw_positional_args: Sequence[Any] = field(default_factory=list)
    manager_inner_mdw_positional_args: Sequence[Any] = field(default_factory=list)

    handler_outer_mdw_positional_args: Sequence[Any] = field(default_factory=list)
    handler_inner_mdw_positional_args: Sequence[Any] = field(default_factory=list)

    filter_positional_args: Sequence[Any] = field(default_factory=list)

    manager_filter_arg_key_template: str = '__eventry_manager_filter_arg_{index}__'
    handler_filter_arg_key_template: str = '__eventry_handler_filter_arg_{index}__'
    handler_arg_key_template: str = '__eventry_handler_arg_{index}__'
    manager_outer_mdw_arg_key_template: str = '__eventry_manager_outer_mdw_arg_{index}__'
    manager_inner_mdw_arg_key_template: str = '__eventry_manager_inner_mdw_arg_{index}__'
    handler_outer_mdw_arg_key_template: str = '__eventry_handler_outer_mdw_arg_{index}__'
    handler_inner_mdw_arg_key_template: str = '__eventry_handler_inner_mdw_arg_{index}__'
