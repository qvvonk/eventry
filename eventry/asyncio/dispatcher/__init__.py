from __future__ import annotations


__all__ = ['Dispatcher', 'DefaultDispatcher', 'ErrorEvent']


from .base import Dispatcher
from .default import ErrorEvent, DefaultDispatcher
