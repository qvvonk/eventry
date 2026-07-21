__all__ = [
    'DefaultRouter'
]

from .base import Router, RouterConfig
from eventry._config import Kwargs, FromKwargs
from eventry.asyncio.handler_manager import DefaultHandlerManager


config = RouterConfig(
    outer_mdw_args=(FromKwargs('next_call'), Kwargs),
    inner_mdw_args=(FromKwargs('next_call'), Kwargs)
)


class DefaultRouter(Router):
    def __init__(self, name: str = ''):
        super().__init__(name=name, config=config)

        self._manager = DefaultHandlerManager('DefaultHandlerManager', lambda *args: True)
        self._handler_managers['DefaultHandlerManager'] = self._manager

    @property
    def on_event(self) -> DefaultHandlerManager:
        return self._manager
