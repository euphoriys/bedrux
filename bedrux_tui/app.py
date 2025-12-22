from __future__ import annotations

import datetime
import textwrap

import psutil
from textual import events
from textual.app import App, ComposeResult
from textual.widgets import Input

from .config import AppConfig
from .controller import ServerController
from .installations import Installation
from .log_buffer import LogBuffer
from .screens import MenuScreen
from .stats import StatsSampler
from .widgets import ClickableRichLog, HistoryInput, ServerStatsWidget


class BedruxMonitorApp(App):
    """Server manager + monitor TUI."""

    CSS_PATH = ["styles.tcss"]

    # Disable command palette completely
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [("escape", "quit", "")]

    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self.config = config or AppConfig()

        self.controller: ServerController | None = None
        self.current_installation: Installation | None = None

        self._server_start_time: datetime.datetime | None = None
        self._log_buffer = LogBuffer(max_messages=self.config.log_buffer_max)
        self._sampler = StatsSampler(cpu_history_size=self.config.cpu_history_size)
        self.cmd_history: list[str] = []

    def compose(self) -> ComposeResult:
        # Screens handle layout.
        yield from ()

    def on_mount(self) -> None:
        self.write_console("Ready.")
        self.push_screen(MenuScreen())
        self._apply_layout_mode()

    async def start_installation(self, installation: Installation) -> None:
        if self.controller and self.controller.is_running():
            self.write_console("Server is already running.")
            return

        self.current_installation = installation
        self.controller = ServerController(
            server_cmd=installation.server_cmd,
            cwd=str(installation.resolved_path()),
            log=self.write_console,
            on_status=self._set_online,
        )

        self._server_start_time = datetime.datetime.now()
        try:
            await self.controller.start()
        except Exception as exc:
            self.write_console(f"Failed to start server: {exc}")
            self._server_start_time = None
            self._set_online(False)

    async def stop_if_running(self) -> None:
        if not self.controller:
            return
        try:
            await self.controller.stop()
        finally:
            self._server_start_time = None
            self._set_online(False)
            self.controller = None
            self.current_installation = None

    async def action_quit(self) -> None:
        await self.stop_if_running()
        self.exit()

    async def stop_current_if_running(self, installation: Installation) -> None:
        if self.current_installation and self.current_installation == installation:
            await self.stop_if_running()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        # Stop event propagation to prevent double execution
        event.stop()

        command = (event.value or "").strip()

        if command:
            if not self.cmd_history or self.cmd_history[-1] != command:
                self.cmd_history.append(command)
                self.cmd_history = self.cmd_history[-200:]

        # Clear the input widget - search in the active screen's DOM
        try:
            inp = self.screen.query_one("#command_input", HistoryInput)
            inp.value = ""
            inp._hist_pos = None
        except Exception:
            return

        if not command:
            return

        if not self.controller or not self.controller.is_running():
            self.write_console("Server is not online.")
            return

        self.write_console(f"> {command}")
        try:
            await self.controller.send_command(command)
        except Exception as exc:
            self.write_console(f"Failed to send command: {exc}")

    def on_resize(self, event: events.Resize) -> None:
        self._reflow_log()
        self._apply_layout_mode()

    def _apply_layout_mode(self) -> None:
        """Apply a compact layout class on short terminals."""
        try:
            height = int(self.size.height)
        except Exception:
            height = 0

        compact = height and height < 40
        try:
            stats = self.screen.query_one(ServerStatsWidget)
            if compact:
                stats.add_class("compact")
            else:
                stats.remove_class("compact")
        except Exception:
            pass

    def write_console(self, message: str) -> None:
        if message is None:
            return

        self._log_buffer.append(str(message))

        try:
            width = max(20, self.size.width - 4)
        except Exception:
            width = 80

        try:
            log_widget = self.screen.query_one("#console_log", ClickableRichLog)
        except Exception:
            # Not in monitor view; keep buffer only.
            return

        for part in str(message).splitlines() or [""]:
            wrapped = textwrap.wrap(part, width=width) or [""]
            for line in wrapped:
                log_widget.write(line)

    def _reflow_log(self) -> None:
        try:
            width = max(20, self.size.width - 4)
        except Exception:
            width = 80

        try:
            log_widget = self.screen.query_one("#console_log", ClickableRichLog)
        except Exception:
            return
        log_widget.clear()
        for line in self._log_buffer.render(width):
            log_widget.write(line)

    def _set_online(self, online: bool) -> None:
        try:
            self.screen.query_one(ServerStatsWidget).is_online = online
        except Exception:
            pass

        if not online:
            self._server_start_time = None
            try:
                self.screen.query_one(ServerStatsWidget).set_uptime(None)
            except Exception:
                pass

    def _tick_stats(self) -> None:
        try:
            stats = self.screen.query_one(ServerStatsWidget)
        except Exception:
            return

        if not self.controller:
            stats.is_online = False
            stats.set_uptime(None)
            return

        pid = self.controller.pid
        if not pid:
            stats.is_online = False
            stats.set_uptime(None)
            return

        try:
            proc = psutil.Process(pid)
        except Exception:
            stats.is_online = False
            stats.set_uptime(None)
            return

        sample = self._sampler.sample(proc)
        if sample is not None:
            stats.set_resources(
                cpu_percent=sample.cpu_percent,
                sys_cpu_percent=sample.sys_cpu_percent,
                raw_cpu_sum=sample.raw_cpu_sum,
                rss_mb=sample.rss_mb,
                total_ram_mb=sample.total_ram_mb,
            )

        stats.set_uptime(self._server_start_time)
