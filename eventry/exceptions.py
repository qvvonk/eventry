from __future__ import annotations


__all__ = ['AbortExecution', 'HandlerNotExecuted']


class AbortExecution(Exception):
    pass


class HandlerNotExecuted(Exception):
    pass


class SkipHandler(Exception):
    pass


class DelayHandler(Exception):
    pass
