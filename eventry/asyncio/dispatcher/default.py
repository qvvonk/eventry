from .base import Dispatcher
from eventry.asyncio.router.default import DefaultRouter


class DefaultDispatcher(Dispatcher, DefaultRouter): ...