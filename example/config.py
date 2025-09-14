from __future__ import annotations

from eventry.config import FromData, HandlerManagerConfig


handler_manager_config = HandlerManagerConfig(
    positional_only_args=(FromData('Event'),),
)
