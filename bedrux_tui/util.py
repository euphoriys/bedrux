from __future__ import annotations

from collections.abc import Iterable
from typing import Optional


def clamp(value: float, lo: float, hi: float) -> float:
    return hi if value > hi else lo if value < lo else value


def is_blank(value: Optional[str]) -> bool:
    return value is None or not str(value).strip()


def keep_last(items: list[str], max_items: int) -> list[str]:
    if max_items <= 0:
        return []
    if len(items) <= max_items:
        return items
    return items[-max_items:]


def split_lines(text: str) -> Iterable[str]:
    return str(text).splitlines() or [""]
