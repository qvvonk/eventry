from __future__ import annotations


__all__ = ['router_logger', 'dispatcher_logger']


from logging import getLogger


router_logger = getLogger('eventry.router')
dispatcher_logger = getLogger('eventry.dispatcher')