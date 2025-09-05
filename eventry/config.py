from typing import TypedDict


class BuiltinNamesRemap(TypedDict, total=False):
    event: str
    dispatcher: str
    router: str
    handler_info: str
    next_call: str


class Config(TypedDict, total=False):
    builtin_names_remap: BuiltinNamesRemap
    positional_only_args: list[str]
    exclude: list[str]