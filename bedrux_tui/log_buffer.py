from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

from .util import keep_last, split_lines


@dataclass(slots=True)
class LogBuffer:
    """Keeps raw log messages and produces width-wrapped output."""

    max_messages: int = 2000
    _messages: list[str] = field(default_factory=list)

    def append(self, message: str) -> None:
        self._messages.append(str(message))
        self._messages = keep_last(self._messages, self.max_messages)

    def render(self, width: int) -> list[str]:
        width = max(20, int(width))
        rendered: list[str] = []
        for msg in self._messages:
            for part in split_lines(msg):
                rendered.append(textwrap.fill(part, width=width))
        return rendered

    def clear(self) -> None:
        self._messages.clear()
