from __future__ import annotations

from typing import Any
from collections.abc import Mapping

from eventry._event import Event


def event_from_context(event: Event, context: Mapping[str, Any]) -> Event:
    return context['event'] if event in context else event
