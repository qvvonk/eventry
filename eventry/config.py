from __future__ import annotations

from typing import TypedDict, Any
from dataclasses import field, dataclass


class FromKwargs:
    def __init__(self, kwargs_param_name: str, /):
        self._val = kwargs_param_name

    @property
    def name(self) -> str:
        return self._val


class DefaultNamesRemap(TypedDict, total=False):
    dispatcher: str
    router: str
    handler_manager: str
    workflow_data: str
    handler: str
    next_call: str
    local_workflow_data: str


@dataclass(frozen=True)
class DispatcherConfig:
    default_names_remap: DefaultNamesRemap = field(default_factory=dict)  # type: ignore
    exclude_names_from_handler_call: list[str] = field(default_factory=list)
    exclude_names_from_filter_call: list[str] = field(default_factory=list)
    exclude_names_from_middleware_call: list[str] = field(default_factory=list)
    single_handler_mode: bool = False


@dataclass(frozen=True)
class HandlerManagerConfig:
    positional_only_args: tuple[Any, ...] = field(default_factory=tuple)
