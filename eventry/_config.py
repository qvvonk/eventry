from __future__ import annotations


__all__ = [
    'HandlerManagerConfig',
    'AsyncEventDispatchingConfig',
]


from typing import Any
from dataclasses import field, dataclass
from collections.abc import Callable, Sequence, Awaitable

from .loggers import logger
from ._execution_context import (
    RouterExecutionContext,
    HandlerExecutionContext,
    ManagerExecutionContext,
)


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
class HandlerManagerConfig:
    manager_outer_mdw_args: Sequence[Any] = field(default_factory=list)
    manager_filter_args: Sequence[Any] = field(default_factory=list)
    manager_inner_mdw_args: Sequence[Any] = field(default_factory=list)

    handler_outer_mdw_args: Sequence[Any] = field(default_factory=list)
    handler_filter_args: Sequence[Any] = field(default_factory=list)
    handler_inner_mdw_args: Sequence[Any] = field(default_factory=list)
    handler_args: Sequence[Any] = field(default_factory=list)

    manager_outer_mdw_arg_key_template: TemplateDescriptor = TemplateDescriptor('__mgr_outer_{index}__')
    manager_filter_arg_key_template: TemplateDescriptor = TemplateDescriptor('__mgr_filter_{index}__')
    manager_inner_mdw_arg_key_template: TemplateDescriptor = TemplateDescriptor('__mgr_inner_{index}__')
    handler_outer_mdw_arg_key_template: TemplateDescriptor = TemplateDescriptor('__handler_outer_{index}__')
    handler_filter_arg_key_template: TemplateDescriptor = TemplateDescriptor('__handler_filter_{index}__')
    handler_inner_mdw_arg_key_template: TemplateDescriptor = TemplateDescriptor('__handler_inner_{index}__')
    handler_arg_key_template: TemplateDescriptor = TemplateDescriptor('__handler_{index}__')

    def collect_manager_outer_mdw_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(
            ctx, self.manager_outer_mdw_arg_key_template, len(self.manager_outer_mdw_args)
        )

    def collect_manager_filter_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(
            ctx, self.manager_filter_arg_key_template, len(self.manager_filter_args)
        )

    def collect_manager_inner_mdw_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(
            ctx, self.manager_inner_mdw_arg_key_template, len(self.manager_inner_mdw_args)
        )

    def collect_handler_outer_mdw_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(
            ctx, self.handler_outer_mdw_arg_key_template, len(self.handler_outer_mdw_args)
        )

    def collect_handler_filter_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(
            ctx, self.handler_filter_arg_key_template, len(self.handler_filter_args)
        )

    def collect_handler_inner_mdw_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(
            ctx, self.handler_inner_mdw_arg_key_template, len(self.handler_inner_mdw_args)
        )

    def collect_handler_args(self, ctx: dict[str, Any]) -> list[Any]:
        return _collect_args(ctx, self.handler_arg_key_template, len(self.handler_args))

    def update_ctx_with_manager_outer_mdw_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(
            ctx, self.manager_outer_mdw_args, self.manager_outer_mdw_arg_key_template
        )

    def update_ctx_with_manager_filter_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(
            ctx, self.manager_filter_args, self.manager_filter_arg_key_template
        )

    def update_ctx_with_manager_inner_mdw_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(
            ctx, self.manager_inner_mdw_args, self.manager_inner_mdw_arg_key_template
        )

    def update_ctx_with_handler_outer_mdw_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(
            ctx, self.handler_outer_mdw_args, self.handler_outer_mdw_arg_key_template
        )

    def update_ctx_with_handler_filter_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(
            ctx, self.handler_filter_args, self.handler_filter_arg_key_template
        )

    def update_ctx_with_handler_inner_mdw_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(
            ctx, self.handler_inner_mdw_args, self.handler_inner_mdw_arg_key_template
        )

    def update_ctx_with_handler_args(self, ctx: dict[str, Any]) -> None:
        update_context_with_args(ctx, self.handler_args, self.handler_arg_key_template)


async def on_error_callback(ctx: RouterExecutionContext, exc: Exception) -> None:
    if not isinstance(ctx, RouterExecutionContext):
        return

    if isinstance(ctx, HandlerExecutionContext):
        logger.error(
            f'An error occurred while executing handler {ctx.handler.id!r} @ {ctx.manager.name!r} @ {ctx.router.full_name}'
            f'for event {ctx.event.name!r}.',
            exc_info=exc,
        )
    elif isinstance(ctx, ManagerExecutionContext):
        logger.error(
            f'An error occurred while executing handlers of manager {ctx.manager.name!r} @ {ctx.router.full_name}.',
            exc_info=exc,
        )
    else:
        logger.error(
            f'An error occurred while executing handlers of router {ctx.router.full_name}.',
            exc_info=exc,
        )


async def on_handler_callback(ctx: HandlerExecutionContext, result: Any) -> None:
    return


@dataclass(kw_only=True)
class AsyncEventDispatchingConfig:
    on_error: Callable[[RouterExecutionContext, Exception], Awaitable[Any]] = on_error_callback
    on_handler: Callable[[HandlerExecutionContext, Any], Awaitable[Any]] = on_handler_callback
