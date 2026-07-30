from __future__ import annotations

from typing import Any
from dataclasses import dataclass
from collections.abc import Sequence


_NEXT_CALL_KEY = 'next_call'


@dataclass(kw_only=True)
class RouterConfig:
    outer_mdw_args: Sequence[Any] = ()
    filter_args: Sequence[Any] = ()
    inner_mdw_args: Sequence[Any] = ()

    outer_mdw_next_call_key = _NEXT_CALL_KEY
    inner_mdw_next_call_key = _NEXT_CALL_KEY


@dataclass(kw_only=True)
class HandlerManagerConfig:
    manager_outer_mdw_args: Sequence[Any] = ()
    manager_filter_args: Sequence[Any] = ()
    manager_inner_mdw_args: Sequence[Any] = ()

    handler_outer_mdw_args: Sequence[Any] = ()
    handler_filter_args: Sequence[Any] = ()
    handler_inner_mdw_args: Sequence[Any] = ()
    handler_args: Sequence[Any] = ()

    manager_outer_mdw_next_call_key = _NEXT_CALL_KEY
    manager_inner_mdw_next_call_key = _NEXT_CALL_KEY
    handler_outer_mdw_next_call_key = _NEXT_CALL_KEY
    handler_inner_mdw_next_call_key = _NEXT_CALL_KEY
