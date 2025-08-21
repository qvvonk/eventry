from typing import Any
from eventry.config import Config

def prepare_kwargs(kwargs: dict[str, Any], config: Config) -> None:
    for old_name, new_name in config.get('builtin_names_remap', {}):
        if old_name in kwargs:
            kwargs[new_name] = kwargs[old_name]
            del kwargs[old_name]

    for excluded_name in config.get('exclude', []):
        if excluded_name in kwargs:
            del kwargs[excluded_name]


def prepare_args(kwargs: dict[str, Any], config: Config) -> list[Any]:
    return [v for i, v in kwargs.items() if v in config.get('positional_only_args', [])]
