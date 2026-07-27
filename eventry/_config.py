from __future__ import annotations

from typing import Any
from dataclasses import dataclass
from collections.abc import Sequence


_NEXT_CALL_KEY = 'next_call'


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


class _TemplateD:
    def __init__(self, default: str) -> None:
        self._default = default

    def __set_name__(self, owner: Any, name: str) -> None:
        self._name = f'_{name}'

    def __get__(self, instance: Any, type: Any) -> str:
        if instance is None:
            return self._default
        return getattr(instance, self._name, self._default)

    def __set__(self, instance: Any, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError('Template must be a string.')
        if '{index}' not in value:
            raise ValueError("Template must contain '{index}'.")
        setattr(instance, self._name, value)


@dataclass(kw_only=True)
class RouterConfig:
    router_key: str = 'router'

    outer_mdw_args: Sequence[Any] = ()
    filter_args: Sequence[Any] = ()
    inner_mdw_args: Sequence[Any] = ()

    outer_mdw_arg_key_template: _TemplateD = _TemplateD('__router_outer_{index}__')
    filter_arg_key_template: _TemplateD = _TemplateD('__router_filter_{index}__')
    inner_arg_key_template: _TemplateD = _TemplateD('__router_inner_{index}__')

    outer_mdw_next_call_key = _NEXT_CALL_KEY
    inner_mdw_next_call_key = _NEXT_CALL_KEY

    def collect_outer_mdw_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(ctx, self.outer_mdw_arg_key_template, len(self.outer_mdw_args))

    def collect_filter_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(ctx, self.filter_arg_key_template, len(self.filter_args))

    def collect_inner_mdw_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(ctx, self.inner_arg_key_template, len(self.inner_mdw_args))

    def update_ctx_with_outer_mdw_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(ctx, self.outer_mdw_args, self.outer_mdw_arg_key_template)

    def update_ctx_with_filter_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(ctx, self.filter_args, self.filter_arg_key_template)

    def update_ctx_with_inner_mdw_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(ctx, self.inner_mdw_args, self.inner_arg_key_template)


@dataclass(kw_only=True)
class HandlerManagerConfig:
    manager_outer_mdw_args: Sequence[Any] = ()
    manager_filter_args: Sequence[Any] = ()
    manager_inner_mdw_args: Sequence[Any] = ()

    handler_outer_mdw_args: Sequence[Any] = ()
    handler_filter_args: Sequence[Any] = ()
    handler_inner_mdw_args: Sequence[Any] = ()
    handler_args: Sequence[Any] = ()

    manager_outer_mdw_arg_key_template: _TemplateD = _TemplateD('__mgr_outer_{index}__')
    manager_filter_arg_key_template: _TemplateD = _TemplateD('__mgr_filter_{index}__')
    manager_inner_mdw_arg_key_template: _TemplateD = _TemplateD('__mgr_inner_{index}__')
    handler_outer_mdw_arg_key_template: _TemplateD = _TemplateD('__handler_outer_{index}__')
    handler_filter_arg_key_template: _TemplateD = _TemplateD('__handler_filter_{index}__')
    handler_inner_mdw_arg_key_template: _TemplateD = _TemplateD('__handler_inner_{index}__')
    handler_arg_key_template: _TemplateD = _TemplateD('__handler_{index}__')

    manager_key: str = 'manager'
    handler_key: str = 'handler'
    manager_outer_mdw_next_call_key = _NEXT_CALL_KEY
    manager_inner_mdw_next_call_key = _NEXT_CALL_KEY
    handler_outer_mdw_next_call_key = _NEXT_CALL_KEY
    handler_inner_mdw_next_call_key = _NEXT_CALL_KEY

    def collect_manager_outer_mdw_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(
            ctx,
            self.manager_outer_mdw_arg_key_template,
            len(self.manager_outer_mdw_args),
        )

    def collect_manager_filter_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(
            ctx,
            self.manager_filter_arg_key_template,
            len(self.manager_filter_args),
        )

    def collect_manager_inner_mdw_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(
            ctx,
            self.manager_inner_mdw_arg_key_template,
            len(self.manager_inner_mdw_args),
        )

    def collect_handler_outer_mdw_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(
            ctx,
            self.handler_outer_mdw_arg_key_template,
            len(self.handler_outer_mdw_args),
        )

    def collect_handler_filter_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(
            ctx,
            self.handler_filter_arg_key_template,
            len(self.handler_filter_args),
        )

    def collect_handler_inner_mdw_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(
            ctx,
            self.handler_inner_mdw_arg_key_template,
            len(self.handler_inner_mdw_args),
        )

    def collect_handler_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(ctx, self.handler_arg_key_template, len(self.handler_args))

    def update_ctx_with_manager_outer_mdw_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(
            ctx,
            self.manager_outer_mdw_args,
            self.manager_outer_mdw_arg_key_template,
        )

    def update_ctx_with_manager_filter_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(
            ctx,
            self.manager_filter_args,
            self.manager_filter_arg_key_template,
        )

    def update_ctx_with_manager_inner_mdw_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(
            ctx,
            self.manager_inner_mdw_args,
            self.manager_inner_mdw_arg_key_template,
        )

    def update_ctx_with_handler_outer_mdw_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(
            ctx,
            self.handler_outer_mdw_args,
            self.handler_outer_mdw_arg_key_template,
        )

    def update_ctx_with_handler_filter_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(
            ctx,
            self.handler_filter_args,
            self.handler_filter_arg_key_template,
        )

    def update_ctx_with_handler_inner_mdw_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(
            ctx,
            self.handler_inner_mdw_args,
            self.handler_inner_mdw_arg_key_template,
        )

    def update_ctx_with_handler_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(ctx, self.handler_args, self.handler_arg_key_template)
