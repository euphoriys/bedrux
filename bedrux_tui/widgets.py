from __future__ import annotations

import datetime

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Input, Label, RichLog, Static


class ClickableRichLog(RichLog):
    """RichLog that clears focus when clicked."""

    def on_mouse_down(self, event: events.MouseDown) -> None:
        try:
            app = getattr(self, "app", None)
            if app is not None:
                app.set_focus(None)
        except Exception:
            pass


class HistoryInput(Input):
    """Input with up/down command history."""

    def on_blur(self) -> None:
        try:
            self._hist_pos = None
        except Exception:
            pass

    def key_escape(self) -> None:
        try:
            app = getattr(self, "app", None)
            if app is not None:
                app.set_focus(None)
        except Exception:
            pass

    def key_up(self) -> None:
        app = getattr(self, "app", None)
        history = getattr(app, "cmd_history", []) if app else []
        if not history:
            return

        pos = getattr(self, "_hist_pos", None)
        if pos is None:
            self._saved = self.value
            pos = len(history) - 1
        else:
            pos = max(0, int(pos) - 1)

        self._hist_pos = pos
        self.value = history[int(pos)]
        self.cursor_position = len(self.value)

    def key_down(self) -> None:
        app = getattr(self, "app", None)
        history = getattr(app, "cmd_history", []) if app else []
        pos = getattr(self, "_hist_pos", None)
        if not history or pos is None:
            return

        pos = int(pos)
        if pos < len(history) - 1:
            pos += 1
            self._hist_pos = pos
            self.value = history[pos]
        else:
            self.value = getattr(self, "_saved", "")
            self._hist_pos = None

        self.cursor_position = len(self.value)


class ServerStatsWidget(Static):
    """Compact server stats - CPU/RAM side by side."""

    is_online = reactive(False)

    def __init__(self, server_name: str = "Server", **kwargs) -> None:
        super().__init__(**kwargs)
        self._server_name = server_name

    def compose(self) -> ComposeResult:
        with Vertical(id="stats_panel"):
            # Status row
            with Horizontal(id="status_row"):
                yield Label(self._server_name, id="server_name")
                yield Label("OFFLINE", id="status_badge", classes="badge_offline")

            # Resource cards
            with Horizontal(id="resource_row"):
                with Vertical(classes="resource_card"):
                    yield Label("CPU", classes="resource_label")
                    yield Label("0%", id="cpu_value", classes="resource_value")

                with Vertical(classes="resource_card"):
                    yield Label("RAM", classes="resource_label")
                    yield Label("0 MB", id="ram_value", classes="resource_value")

            # Uptime
            with Horizontal(id="uptime_row"):
                yield Label("Uptime:", id="uptime_label")
                yield Label("00:00:00", id="uptime_value")

    def watch_is_online(self, online: bool) -> None:
        try:
            badge = self.query_one("#status_badge", Label)
            if online:
                badge.update("ONLINE")
                badge.remove_class("badge_offline")
                badge.add_class("badge_online")
            else:
                badge.update("OFFLINE")
                badge.remove_class("badge_online")
                badge.add_class("badge_offline")
                self.query_one("#cpu_value", Label).update("0%")
                self.query_one("#ram_value", Label).update("0 MB")
        except Exception:
            pass

    def on_mouse_down(self, event: events.MouseDown) -> None:
        try:
            app = getattr(self, "app", None)
            if app is not None:
                app.set_focus(None)
        except Exception:
            pass

    def set_resources(
        self,
        *,
        cpu_percent: float,
        sys_cpu_percent: float,
        raw_cpu_sum: float,
        rss_mb: int,
        total_ram_mb: int,
    ) -> None:
        try:
            self.query_one("#cpu_value", Label).update(f"{cpu_percent:.0f}%")
            self.query_one("#ram_value", Label).update(f"{rss_mb} MB")
        except Exception:
            pass

    def set_uptime(self, start_time: datetime.datetime | None) -> None:
        try:
            label = self.query_one("#uptime_value", Label)
            if not start_time:
                label.update("00:00:00")
                return
            delta = datetime.datetime.now() - start_time
            label.update(str(delta).split(".")[0])
        except Exception:
            pass

    def set_server_name(self, name: str) -> None:
        try:
            self.query_one("#server_name", Label).update(name)
        except Exception:
            pass
