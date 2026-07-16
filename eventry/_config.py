__all__ = [
    'HandlerManagerConfig',
]


from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


def _collect_args(di: dict[str, Any], template: str, amount: int | None = None) -> list[Any]:
    if amount is None:
        result = []
        index = 0
        while True:
            key = template.format(index)
            if key not in di:
                return result
            result.append(di[key])
            index += 1
    else:
        return [di[template.format(index=i)] for i in range(amount)] if amount else []


def update_context_with_args(di: dict[str, Any], args: Sequence[Any], template: str) -> None:
    for index, arg in enumerate(args):
        di[template.format(index=index)] = arg


class TemplateDescriptor:
    def __init__(self, value: str) -> None:
        self._value = value

    def __get__(self, *args: Any) -> str:
        return self._value

    def __set__(self, instance: Any, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError('Template must be a string.')
        if '{index}' not in value:
            raise ValueError('Template must contain \'{index}\'.')
        self._value = value


@dataclass(kw_only=True)
class HandlerManagerConfig:
    isolate_handler_context: bool = True

    manager_outer_mdw_args: Sequence[Any] = field(default_factory=list)
    manager_filter_args: Sequence[Any] = field(default_factory=list)
    manager_inner_mdw_args: Sequence[Any] = field(default_factory=list)

    handler_outer_mdw_args: Sequence[Any] = field(default_factory=list)
    handler_filter_args: Sequence[Any] = field(default_factory=list)
    handler_inner_mdw_args: Sequence[Any] = field(default_factory=list)
    handler_args: Sequence[Any] = field(default_factory=list)

    manager_outer_mdw_arg_key_template: str = TemplateDescriptor('__mgr_outer_{index}__')
    manager_filter_arg_key_template: str = TemplateDescriptor('__mgr_filter_{index}__')
    manager_inner_mdw_arg_key_template: str = TemplateDescriptor('__mgr_inner_{index}__')
    handler_outer_mdw_arg_key_template: str = TemplateDescriptor('__handler_outer_{index}__')
    handler_filter_arg_key_template: str = TemplateDescriptor('__handler_filter_{index}__')
    handler_inner_mdw_arg_key_template: str = TemplateDescriptor('__handler_inner_{index}__')
    handler_arg_key_template: str = TemplateDescriptor('__handler_{index}__')

    def collect_manager_outer_mdw_args(self, di: dict[str, Any]) -> list[Any]:
        return _collect_args(di, self.manager_outer_mdw_arg_key_template, len(self.manager_outer_mdw_args))

    def collect_manager_filter_args(self, di: dict[str, Any]) -> list[Any]:
        return _collect_args(di, self.manager_filter_arg_key_template, len(self.manager_filter_args))

    def collect_manager_inner_mdw_args(self, di: dict[str, Any]) -> list[Any]:
        return _collect_args(di, self.manager_inner_mdw_arg_key_template, len(self.manager_inner_mdw_args))

    def collect_handler_outer_mdw_args(self, di: dict[str, Any]) -> list[Any]:
        return _collect_args(di, self.handler_outer_mdw_arg_key_template, len(self.handler_outer_mdw_args))

    def collect_handler_filter_args(self, di: dict[str, Any]) -> list[Any]:
        return _collect_args(di, self.handler_filter_arg_key_template, len(self.handler_filter_args))

    def collect_handler_inner_mdw_args(self, di: dict[str, Any]) -> list[Any]:
        return _collect_args(di, self.handler_inner_mdw_arg_key_template, len(self.handler_inner_mdw_args))

    def collect_handler_args(self, di: dict[str, Any]) -> list[Any]:
        return _collect_args(di, self.handler_arg_key_template, len(self.handler_args))

    def update_di_with_manager_outer_mdw_args(self, di: dict[str, Any]) -> None:
        update_context_with_args(di, self.manager_outer_mdw_args,
                                 self.manager_outer_mdw_arg_key_template)

    def update_di_with_manager_filter_args(self, di: dict[str, Any]) -> None:
        update_context_with_args(di, self.manager_filter_args,
                                 self.manager_filter_arg_key_template)

    def update_di_with_manager_inner_mdw_args(self, di: dict[str, Any]) -> None:
        update_context_with_args(di, self.manager_inner_mdw_args,
                                 self.manager_inner_mdw_arg_key_template)

    def update_di_with_handler_outer_mdw_args(self, di: dict[str, Any]) -> None:
        update_context_with_args(di, self.handler_outer_mdw_args,
                                 self.handler_outer_mdw_arg_key_template)

    def update_di_with_handler_filter_args(self, di: dict[str, Any]) -> None:
        update_context_with_args(di, self.handler_filter_args,
                                 self.handler_filter_arg_key_template)

    def update_di_with_handler_inner_mdw_args(self, di: dict[str, Any]) -> None:
        update_context_with_args(di, self.handler_inner_mdw_args,
                                 self.handler_inner_mdw_arg_key_template)

    def update_di_with_handler_args(self, di: dict[str, Any]) -> None:
        update_context_with_args(di, self.handler_args, self.handler_arg_key_template)