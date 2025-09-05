from typing import TypedDict
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


class BuiltinNamesRemap(TypedDict, total=False):
    event: str
    dispatcher: str
    router: str
    handler_info: str
    next_call: str
    local_workflow_data: str


@dataclass(frozen=True)
class DispatcherConfig:
    builtin_names_remap: BuiltinNamesRemap = field(default_factory=lambda: MappingProxyType({}))
    exclude: tuple[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class HandlerManagerConfig:
    positional_args: tuple[str | Any] = field(default_factory=tuple)
