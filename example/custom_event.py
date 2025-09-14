from __future__ import annotations

from typing import Any

from eventry.asyncio.event import ExtendedEvent


class MyEvent(ExtendedEvent):
    def __init__(self, object: str):
        super().__init__()
        self._object: str = object

    @property
    def object(self) -> str:
        return self._object

    @property
    def workflow_injection(self) -> dict[str, Any]:
        return {'object': self.object}
