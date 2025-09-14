from __future__ import annotations

from eventry.config import FromKwargs, HandlerManagerConfig


handler_manager_config = HandlerManagerConfig(
    positional_only_args=(FromKwargs('Event'),),
)
