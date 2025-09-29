from __future__ import annotations


__all__ = ['Return', 'HandlerNotExecuted']


class Return(Exception):
    pass


class HandlerNotExecuted(Exception):
    pass


class SkipHandler(Exception):
    pass


class DelayHandler(Exception):
    pass
