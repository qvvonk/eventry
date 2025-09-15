from __future__ import annotations

from eventry.config import FromData, HandlerManagerConfig


handler_manager_config = HandlerManagerConfig(
    handler_positional_only_args=(FromData('Event'),),
)
