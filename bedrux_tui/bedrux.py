"""Entry point for the Bedrux Textual TUI monitor.

This module is intentionally small; the implementation lives in the
`server/bedrux_tui/` package.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


# Ensure `server/` is importable so `bedrux_tui` can be found even when this
# file is launched by tools that don't set sys.path like `python server/...`.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def main() -> None:
    # Try normal package imports first (when installed)
    try:
        from bedrux_tui import BedruxMonitorApp
        from bedrux_tui.config import AppConfig
        from bedrux_tui.downloader import ensure_bedrux_home
    except Exception:
        # Fallback: load sibling modules directly from files so the script
        # works when executed from the source tree (python bedrux.py).
        import importlib.util

        def _load(name: str, path: Path):
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(mod)
            return mod

        _app = _load("bedrux_tui.app", _HERE / "app.py")
        _config = _load("bedrux_tui.config", _HERE / "config.py")
        _downloader = _load("bedrux_tui.downloader", _HERE / "downloader.py")

        BedruxMonitorApp = getattr(_app, "BedruxMonitorApp")
        AppConfig = getattr(_config, "AppConfig")
        ensure_bedrux_home = getattr(_downloader, "ensure_bedrux_home")

    # Ensure bedrux home exists and migrate from /opt if needed
    try:
        ensure_bedrux_home()
    except Exception:
        # Non-fatal: proceed even if ensure step fails
        pass

    server_cmd = os.environ.get("BEDRUX_SERVER_CMD", "./bedrock_server")
    app = BedruxMonitorApp(AppConfig(server_cmd=server_cmd))
    app.run()


if __name__ == "__main__":
    main()
