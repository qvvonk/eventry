from __future__ import annotations


__all__ = ['DefaultHandlerManager']


from typing import TYPE_CHECKING
from functools import partial
from eventry.asyncio.middleware_manager import MiddlewareStorage

from .base import HandlerManager


if TYPE_CHECKING:
    from eventry._config import HandlerManagerConfig
    from .base import EventFilter


class DefaultHandlerManager(HandlerManager):
    def __init__(
        self,
        name: str,
        event_filter: EventFilter | None = None,
        config: HandlerManagerConfig | None = None,
    ) -> None:
        super().__init__(
            name=name,
            event_filter=event_filter,
            config=config,
        )

        self.middleware.set_middlewares_storage('manager.outer', MiddlewareStorage())
        self.middleware.set_middlewares_storage('manager.inner', MiddlewareStorage())
        self.middleware.set_middlewares_storage('handler.outer', MiddlewareStorage())
        self.middleware.set_middlewares_storage('handler.inner', MiddlewareStorage())

    # Use partial to keep the decorator syntax consistent:
    # all decorators are called with parentheses.
    # todo: type hints
    @property
    def manager_outer_middleware(self):
        return partial(self.middleware, scope='manager.outer')

    @property
    def manager_inner_middleware(self):
        return partial(self.middleware, scope='manager.inner')

    @property
    def handler_outer_middleware(self):
        return partial(self.middleware, scope='handler.outer')

    @property
    def handler_inner_middleware(self):
        return partial(self.middleware, scope='handler.inner')
