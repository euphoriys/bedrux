from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Runtime configuration for the TUI."""

    server_cmd: str = "./bedrock_server"
    stats_interval_s: float = 1.0
    cpu_history_size: int = 5
    log_buffer_max: int = 2000
