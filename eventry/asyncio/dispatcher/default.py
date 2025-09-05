from .base import Dispatcher
from eventry.asyncio.router.default import DefaultRouter
from typing import Any


class DefaultDispatcher(Dispatcher, DefaultRouter):
    def __init__(self, workflow_data: dict[str, Any] | None = None) -> None:
        super().__init__(workflow_data)