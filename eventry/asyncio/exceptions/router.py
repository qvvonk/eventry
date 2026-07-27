from __future__ import annotations

from .base import EventryException


__all__ = [
    'RouterError',
    'RouterAttachmentError',
    'RouterAlreadyAttachedError',
    'DuplicateSubrouterNameError',
    'RouterLoopError',
]


class RouterError(EventryException): ...


# --- Router attachment exceptions ---
class RouterAttachmentError(RouterError): ...


class RouterAlreadyAttachedError(RouterAttachmentError, ValueError): ...


class DuplicateSubrouterNameError(RouterAttachmentError, ValueError): ...


class RouterLoopError(RouterAttachmentError, ValueError): ...
