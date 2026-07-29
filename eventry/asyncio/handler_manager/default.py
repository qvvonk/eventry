from __future__ import annotations


__all__ = ['DefaultHandlerManager']


from typing import TYPE_CHECKING
from functools import partial

from eventry.asyncio.config import Kwargs, FromKwargs
from eventry.asyncio.middleware import MiddlewareStorage
from eventry.asyncio.handler_manager.base import HandlerManager, HandlerManagerConfig


if TYPE_CHECKING:
    from .base import EventFilter


config = HandlerManagerConfig(
    manager_outer_mdw_args=(FromKwargs('next_call'), Kwargs),
    manager_inner_mdw_args=(FromKwargs('next_call'), Kwargs),
    handler_outer_mdw_args=(FromKwargs('next_call'), Kwargs),
    handler_inner_mdw_args=(FromKwargs('next_call'), Kwargs),
)


class DefaultHandlerManager(HandlerManager):
    def __init__(
        self,
        name: str,
        event_filter: EventFilter | None = None,
    ) -> None:
        super().__init__(name=name, event_filter=event_filter, config=config)

        self.middleware.set_middlewares_storage('manager.outer', MiddlewareStorage())
        self.middleware.set_middlewares_storage('manager.inner', MiddlewareStorage())
        self.middleware.set_middlewares_storage('handler.outer', MiddlewareStorage())
        self.middleware.set_middlewares_storage('handler.inner', MiddlewareStorage())

    @property
    def manager_outer_middleware(self) -> MiddlewareStorage:
        return self.middleware.get_middlewares_storage('manager.outer', raise_=True)

    @property
    def manager_inner_middleware(self) -> MiddlewareStorage:
        return self.middleware.get_middlewares_storage('manager.inner', raise_=True)

    @property
    def handler_outer_middleware(self) -> MiddlewareStorage:
        return self.middleware.get_middlewares_storage('handler.outer', raise_=True)

    @property
    def handler_inner_middleware(self) -> MiddlewareStorage:
        return self.middleware.get_middlewares_storage('handler.inner', raise_=True)
