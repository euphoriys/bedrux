from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional

import psutil

from .util import clamp


@dataclass(slots=True)
class ResourceSample:
    cpu_percent: float
    sys_cpu_percent: float
    raw_cpu_sum: float
    rss_mb: int
    total_ram_mb: int


class StatsSampler:
    """Samples CPU and RAM usage for a process + its children."""

    def __init__(self, *, cpu_history_size: int = 5) -> None:
        self._cpu_history = deque(maxlen=max(1, int(cpu_history_size)))
        self._cpu_count = psutil.cpu_count(logical=True) or 1
        self._warmed = False

        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

    def sample(self, proc: psutil.Process) -> Optional[ResourceSample]:
        try:
            procs = [proc] + proc.children(recursive=True)
        except Exception:
            procs = [proc]

        cpu_sum = 0.0
        rss_bytes = 0

        for p in procs:
            try:
                cpu_sum += p.cpu_percent(interval=None)
                rss_bytes += p.memory_info().rss
            except Exception:
                continue

        if not self._warmed:
            for p in procs:
                try:
                    p.cpu_percent(interval=None)
                except Exception:
                    pass
            self._warmed = True
            return None

        rss_mb = max(0, int(rss_bytes / 1024 / 1024))

        normalized = cpu_sum / self._cpu_count if self._cpu_count else cpu_sum
        cpu_display = clamp(normalized, 0.0, 100.0)

        self._cpu_history.append(cpu_display)
        cpu_smoothed = sum(self._cpu_history) / len(self._cpu_history)

        try:
            sys_cpu = float(psutil.cpu_percent(interval=None))
        except Exception:
            sys_cpu = 0.0

        try:
            total_ram_mb = int(psutil.virtual_memory().total / 1024 / 1024)
        except Exception:
            total_ram_mb = max(4096, rss_mb)

        return ResourceSample(
            cpu_percent=float(cpu_smoothed),
            sys_cpu_percent=float(sys_cpu),
            raw_cpu_sum=float(cpu_sum),
            rss_mb=rss_mb,
            total_ram_mb=max(1, total_ram_mb),
        )
