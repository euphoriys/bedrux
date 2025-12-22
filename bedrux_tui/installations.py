from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def get_server_command_for_arch() -> str:
    """Get the appropriate server command based on system architecture."""
    arch = platform.machine()
    if arch == "aarch64":
        return "box64 bedrock_server"
    elif arch == "x86_64":
        return "./bedrock_server"
    else:
        # Fallback for unknown architectures
        return "./bedrock_server"


# Default server command based on current system architecture
DEFAULT_SERVER_CMD = get_server_command_for_arch()


@dataclass(frozen=True, slots=True)
class Installation:
    name: str
    path: str
    server_cmd: str = DEFAULT_SERVER_CMD

    def resolved_path(self) -> Path:
        return Path(self.path).expanduser().resolve()


def default_store_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else (Path.home() / ".config")
    return base / "bedrux" / "installations.json"


class InstallationStore:
    def __init__(self, store_path: Path | None = None) -> None:
        self.store_path = store_path or default_store_path()

    def load(self) -> list[Installation]:
        path = self.store_path
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

        items: list[Installation] = []
        if isinstance(data, list):
            for raw in data:
                inst = _parse_installation(raw)
                if inst:
                    items.append(inst)
        return items

    def save(self, installations: list[Installation]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(i) for i in installations]
        self.store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def discover_installations(roots: list[Path]) -> list[Installation]:
    found: list[Installation] = []
    for root in roots:
        try:
            root = root.expanduser().resolve()
        except Exception:
            continue
        if not root.exists() or not root.is_dir():
            continue

        # Direct root is an installation
        if _has_bedrock_binary(root):
            found.append(Installation(name=root.name, path=str(root)))
            continue

        # One-level scan
        try:
            for child in root.iterdir():
                if child.is_dir() and _has_bedrock_binary(child):
                    found.append(Installation(name=child.name, path=str(child)))
        except Exception:
            continue

    # De-dupe by resolved path
    seen: set[str] = set()
    unique: list[Installation] = []
    for inst in found:
        try:
            key = str(inst.resolved_path())
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append(inst)
    return unique


def _has_bedrock_binary(folder: Path) -> bool:
    return (folder / "bedrock_server").exists() or (folder / "bedrock_server.exe").exists()


def _parse_installation(raw: Any) -> Installation | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    path = str(raw.get("path") or "").strip()
    server_cmd = str(raw.get("server_cmd") or "./bedrock_server").strip()
    if not name or not path:
        return None
    return Installation(name=name, path=path, server_cmd=server_cmd)
