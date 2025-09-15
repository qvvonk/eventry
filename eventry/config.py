from __future__ import annotations

from typing import Any, TypedDict
from dataclasses import field, dataclass


class FromData(str): ...


class DefaultNamesRemap(TypedDict, total=False):
    event: str
    dispatcher: str
    router: str
    handler_manager: str
    workflow_data: str
    data: str
    handler: str
    executed_handlers: str
    workflow_data_injection: str


@dataclass(frozen=True)
class DispatcherConfig:
    default_names_remap: DefaultNamesRemap = field(default_factory=dict)  # type: ignore
    single_handler_mode: bool = False


@dataclass(frozen=True)
class HandlerManagerConfig:
    handler_positional_only_args: tuple[Any, ...] = field(default_factory=tuple)
    exclude_from_handler_call: frozenset[str] = field(default_factory=frozenset)

    middleware_positional_only_args: tuple[Any, ...] = field(default_factory=tuple)
    exclude_from_middleware_call: frozenset[str] = field(default_factory=frozenset)

    filter_positional_only_args: tuple[Any, ...] = field(default_factory=tuple)
    exclude_from_filter_call: frozenset[str] = field(default_factory=frozenset)
