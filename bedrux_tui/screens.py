"""Bedrux TUI Screens - Clean Mobile-Optimized Design."""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, ListItem, ListView, Static, ProgressBar

from .backup import make_backup, restore_backup, list_backups, delete_backup, BackupInfo
from .installations import Installation, InstallationStore, discover_installations
from .widgets import ClickableRichLog, HistoryInput, ServerStatsWidget
from .downloader import (
    fetch_versions,
    download_and_install,
    make_version_url,
    validate_instance_name,
    validate_version_format,
    get_bedrux_home,
    get_server_command,
    VersionInfo,
)

if TYPE_CHECKING:
    from .app import BedruxMonitorApp


class MonitorScreen(Screen):
    """Server monitoring screen."""

    BINDINGS = [
        ("escape", "back", ""),
        ("x", "stop_server", ""),
        ("s", "start_server", ""),
    ]

    def __init__(self, installation: Installation) -> None:
        super().__init__()
        self.installation = installation

    def compose(self) -> ComposeResult:
        yield ServerStatsWidget(server_name=self.installation.name)
        yield ClickableRichLog(
            highlight=True,
            markup=False,
            wrap=True,
            id="console_log"
        )
        yield HistoryInput(
            placeholder="Command...",
            id="command_input"
        )

    def on_mount(self) -> None:
        app = cast("BedruxMonitorApp", self.app)

        try:
            app._reflow_log()
        except Exception:
            pass

        try:
            self.set_focus(self.query_one("#command_input", Input))
        except Exception:
            pass

        try:
            stats = self.query_one(ServerStatsWidget)
            stats.set_server_name(self.installation.name)
        except Exception:
            pass

        app.write_console(f"Server: {self.installation.name}")
        app.write_console(f"Path: {self.installation.path}")
        app.set_interval(app.config.stats_interval_s, app._tick_stats)

    def action_blur(self) -> None:
        try:
            self.set_focus(None)
        except Exception:
            pass

    async def action_back(self) -> None:
        app = cast("BedruxMonitorApp", self.app)
        await app.stop_if_running()
        app.pop_screen()

    async def action_stop_server(self) -> None:
        app = cast("BedruxMonitorApp", self.app)
        await app.stop_if_running()

    async def action_start_server(self) -> None:
        """Start server if not running (triggered by 's' key)."""
        app = cast("BedruxMonitorApp", self.app)
        if app.controller and app.controller.is_running():
            return
        try:
            await app.start_installation(self.installation)
        except Exception:
            pass


class MenuScreen(Screen):
    """Main menu screen."""

    BINDINGS = [
        ("a", "add", ""),
        ("d", "delete", ""),
        ("enter", "start", ""),
        ("up", "select_prev", ""),
        ("down", "select_next", ""),
        ("b", "backup", ""),
        ("r", "restore", ""),
        ("escape", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._store = InstallationStore()
        self._installations: list[Installation] = []
        self._explicitly_selected: bool = False  # Track if user explicitly selected an item
        self._last_click_time: float = 0.0  # For double-click detection
        self._last_click_index: int | None = None  # Track which item was clicked
        self._double_click_threshold: float = 0.4  # 400ms for double-click

    def compose(self) -> ComposeResult:
        with Vertical(id="menu_container"):
            yield Static("BEDRUX", id="main_title")

            with Vertical(id="list_card"):
                yield ListView(id="installations")

            with Vertical(id="action_buttons"):
                with Horizontal(id="btn_row_top"):
                    yield Button("Add", id="btn_add")
                    yield Button("Delete", id="btn_delete", variant="error")

                with Horizontal(id="btn_row_bottom"):
                    yield Button("Backup", id="btn_backup")
                    yield Button("Restore", id="btn_restore")

        yield Footer()

    def on_mount(self) -> None:
        self._load_installations()
        self._render_list()
        try:
            self.set_focus(self.query_one("#installations", ListView))
        except Exception:
            pass

    def _load_installations(self) -> None:
        items = self._store.load()
        if items:
            self._installations = items
            return

        bedrux_home = get_bedrux_home()
        roots = [bedrux_home, Path.cwd() / "server", Path.cwd()]
        discovered = discover_installations(roots)
        self._installations = discovered
        if discovered:
            self._store.save(discovered)

    def _render_list(self) -> None:
        lv = self.query_one("#installations", ListView)
        lv.clear()

        for inst in self._installations:
            lv.append(ListItem(Label(inst.name)))

        # Don't auto-select - user must click to select
        if self._installations:
            lv.index = None
        self._explicitly_selected = False

    def _selected(self) -> Installation | None:
        lv = self.query_one("#installations", ListView)
        idx = lv.index
        # Only return selected if user explicitly selected
        if not self._explicitly_selected:
            return None
        if idx is None or idx < 0 or idx >= len(self._installations):
            return None
        return self._installations[idx]

    def action_select_prev(self) -> None:
        lv = self.query_one("#installations", ListView)
        if lv.index is None:
            lv.index = 0 if self._installations else None
            self._explicitly_selected = True
            return
        lv.index = max(0, int(lv.index) - 1)
        self._explicitly_selected = True

    def action_select_next(self) -> None:
        lv = self.query_one("#installations", ListView)
        if not self._installations:
            lv.index = None
            return
        if lv.index is None:
            lv.index = 0
            self._explicitly_selected = True
            return
        lv.index = min(len(self._installations) - 1, int(lv.index) + 1)
        self._explicitly_selected = True

    async def action_quit(self) -> None:
        app = cast("BedruxMonitorApp", self.app)
        await app.stop_if_running()
        app.exit()

    def action_add(self) -> None:
        self.app.push_screen(
            AddInstallationScreen(
                self._store,
                self._installations,
                on_done=self._on_added
            )
        )

    def _on_added(self) -> None:
        self._installations = self._store.load()
        self._render_list()

    async def action_delete(self) -> None:
        inst = self._selected()
        if not inst:
            return

        # Delete the actual folder
        try:
            folder = inst.resolved_path()
            if folder.exists():
                await asyncio.to_thread(shutil.rmtree, folder)
        except Exception:
            pass

        # Remove from list and save
        self._installations = [i for i in self._installations if i != inst]
        self._store.save(self._installations)
        self._render_list()

    async def action_start(self) -> None:
        inst = self._selected()
        if not inst:
            return
        app = cast("BedruxMonitorApp", self.app)
        app.push_screen(MonitorScreen(inst))
        try:
            await app.start_installation(inst)
        except Exception:
            pass

    async def action_backup(self) -> None:
        inst = self._selected()
        if not inst:
            return

        try:
            result = await asyncio.to_thread(
                make_backup,
                inst.resolved_path(),
                inst.name
            )
            # Show success notification
            app = cast("BedruxMonitorApp", self.app)
            if hasattr(app, 'notify'):
                app.notify(f"Backup created: {result.archive_path.name}")
        except Exception:
            pass

    def action_restore(self) -> None:
        self.app.push_screen(RestoreScreen(self._store, self._installations, on_done=self._on_added))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "btn_add":
                self.action_add()
            case "btn_delete":
                await self.action_delete()
            case "btn_backup":
                await self.action_backup()
            case "btn_restore":
                self.action_restore()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Single click highlights/selects an item."""
        self._explicitly_selected = True

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """
        Handle ListView selection - implement double-click detection.
        Single click = select only
        Double click = start server
        """
        current_time = time.time()
        lv = self.query_one("#installations", ListView)
        current_index = lv.index

        # Check if this is a double-click (same item clicked within threshold)
        is_double_click = (
            self._last_click_index is not None and
            self._last_click_index == current_index and
            (current_time - self._last_click_time) < self._double_click_threshold
        )

        # Update click tracking
        self._last_click_time = current_time
        self._last_click_index = current_index
        self._explicitly_selected = True

        # Only start server on double-click
        if is_double_click:
            # Reset to prevent triple-click starting again
            self._last_click_time = 0.0
            self._last_click_index = None
            await self.action_start()


class AddInstallationScreen(Screen):
    """Add new installation screen - Downloads from Minecraft.net."""

    BINDINGS = [
        ("escape", "back", ""),
    ]

    def __init__(
        self,
        store: InstallationStore,
        existing: list[Installation],
        *,
        on_done: Callable[[], None],
    ) -> None:
        super().__init__()
        self._store = store
        self._existing = existing
        self._on_done = on_done
        self._versions: list[VersionInfo] = []
        self._selected_url: str | None = None
        self._is_installing = False

    def compose(self) -> ComposeResult:
        with Vertical(id="add_container"):
            with Vertical(id="add_form"):
                yield Static("Create New Instance", id="form_title")

                yield Label("Instance name:", classes="field_label")
                yield Input(
                    placeholder="MyServer",
                    id="instance_name",
                    classes="field_input"
                )

                yield Label("Select version:", classes="field_label")
                yield ListView(id="version_list")

                yield Label("Or enter custom version:", classes="field_label")
                yield Input(
                    placeholder="1.21.0.3",
                    id="custom_version",
                    classes="field_input"
                )

                yield Static("", id="status_label", classes="field_label")
                yield ProgressBar(id="progress_bar", show_eta=False, show_percentage=True)

                with Horizontal(id="add_buttons"):
                    yield Button("Fetch Versions", id="btn_fetch", variant="primary")
                    yield Button("Install", id="btn_install", variant="success")
                    yield Button("Cancel", id="btn_cancel")

    def on_mount(self) -> None:
        try:
            self.set_focus(self.query_one("#instance_name", Input))
        except Exception:
            pass

        # Hide progress bar initially
        try:
            self.query_one("#progress_bar", ProgressBar).display = False
        except Exception:
            pass

        # Auto-fetch versions on mount
        self.run_worker(self._fetch_versions(), exclusive=True)

    def action_back(self) -> None:
        if self._is_installing:
            return  # Prevent going back during installation
        self.app.pop_screen()

    def _set_status(self, message: str) -> None:
        try:
            self.query_one("#status_label", Static).update(message)
        except Exception:
            pass

    def _update_progress(self, current: int, total: int) -> None:
        try:
            progress = self.query_one("#progress_bar", ProgressBar)
            if total > 0:
                progress.update(total=total, progress=current)
        except Exception:
            pass

    async def _fetch_versions(self) -> None:
        self._set_status("Fetching versions from Minecraft Wiki...")

        try:
            self._versions = await fetch_versions(log=self._set_status)
        except Exception as e:
            self._set_status(f"Error fetching versions: {e}")
            return

        # Update version list
        try:
            version_list = self.query_one("#version_list", ListView)
            version_list.clear()

            for v in self._versions:
                version_list.append(ListItem(Label(v.display_name)))

            if self._versions:
                version_list.index = 0
                self._set_status(f"Found {len(self._versions)} version(s). Select one or enter custom version.")
            else:
                self._set_status("No versions found. Enter a custom version.")
        except Exception as e:
            self._set_status(f"Error displaying versions: {e}")

    async def _install_instance(self) -> None:
        if self._is_installing:
            return

        self._is_installing = True

        # Disable buttons during installation
        try:
            self.query_one("#btn_fetch", Button).disabled = True
            self.query_one("#btn_install", Button).disabled = True
            self.query_one("#btn_cancel", Button).disabled = True
        except Exception:
            pass

        # Get instance name
        name_input = self.query_one("#instance_name", Input)
        instance_name = name_input.value.strip()

        # Validate instance name
        valid, error = validate_instance_name(instance_name)
        if not valid:
            self._set_status(f"Error: {error}")
            self._is_installing = False
            self._enable_buttons()
            return

        # Check if instance already exists
        bedrux_home = get_bedrux_home()
        instance_path = bedrux_home / "instances" / instance_name
        if instance_path.exists():
            self._set_status(f"Error: Instance '{instance_name}' already exists.")
            self._is_installing = False
            self._enable_buttons()
            return

        # Determine URL
        url: str | None = None

        # First check custom version
        custom_version = self.query_one("#custom_version", Input).value.strip()
        if custom_version:
            if not validate_version_format(custom_version):
                self._set_status("Error: Invalid version format. Use format like 1.21.0.3")
                self._is_installing = False
                self._enable_buttons()
                return

            self._set_status(f"Checking version {custom_version}...")
            url = await make_version_url(custom_version, log=self._set_status)

            if not url:
                self._set_status(f"Error: Version {custom_version} not found on Minecraft.net")
                self._is_installing = False
                self._enable_buttons()
                return
        else:
            # Use selected version from list
            try:
                version_list = self.query_one("#version_list", ListView)
                idx = version_list.index
                if idx is not None and 0 <= idx < len(self._versions):
                    url = self._versions[idx].download_url
                    self._set_status(f"Using {self._versions[idx].display_name}")
            except Exception:
                pass

        if not url:
            self._set_status("Error: No version selected. Fetch versions or enter custom version.")
            self._is_installing = False
            self._enable_buttons()
            return

        # Show progress bar
        try:
            progress = self.query_one("#progress_bar", ProgressBar)
            progress.display = True
            progress.update(total=100, progress=0)
        except Exception:
            pass

        # Download and install
        self._set_status("[+] Starting installation...")

        try:
            success = await download_and_install(
                url=url,
                instance_name=instance_name,
                bedrux_home=bedrux_home,
                log=self._set_status,
                progress=self._update_progress,
                overwrite=False,
            )
        except Exception as e:
            self._set_status(f"Error: {e}")
            self._is_installing = False
            self._enable_buttons()
            return

        if not success:
            self._is_installing = False
            self._enable_buttons()
            return

        # Add to installations list
        server_cmd = get_server_command()
        new_installation = Installation(
            name=instance_name,
            path=str(instance_path),
            server_cmd=server_cmd,
        )

        merged = list(self._existing)
        merged.append(new_installation)
        self._store.save(merged)

        self._set_status(f"[✓] Instance '{instance_name}' created successfully!")

        # Wait a moment so user sees success message
        await asyncio.sleep(1.5)

        self._is_installing = False
        self.app.pop_screen()
        self._on_done()

    def _enable_buttons(self) -> None:
        try:
            self.query_one("#btn_fetch", Button).disabled = False
            self.query_one("#btn_install", Button).disabled = False
            self.query_one("#btn_cancel", Button).disabled = False
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "btn_fetch":
                self.run_worker(self._fetch_versions(), exclusive=True)
            case "btn_install":
                self.run_worker(self._install_instance(), exclusive=True)
            case "btn_cancel":
                self.action_back()


class RestoreScreen(Screen):
    """Restore backup screen - shows list of available backups."""

    BINDINGS = [
        ("escape", "back", ""),
        ("enter", "restore", ""),
        ("d", "delete_backup", ""),
        ("r", "refresh", ""),
    ]

    def __init__(
        self,
        store: InstallationStore,
        existing: list[Installation],
        *,
        on_done: Callable[[], None],
    ) -> None:
        super().__init__()
        self._store = store
        self._existing = existing
        self._on_done = on_done
        self._backups: list[BackupInfo] = []
        self._is_restoring = False

    def compose(self) -> ComposeResult:
        with Vertical(id="restore_container"):
            with Vertical(id="restore_form"):
                yield Static("Restore Backup", id="form_title")

                yield Label("Available backups:", classes="field_label")
                yield ListView(id="backup_list")

                yield Label("New instance name (optional):", classes="field_label")
                yield Input(
                    placeholder="Leave empty to use original name",
                    id="new_name",
                    classes="field_input"
                )

                yield Static("", id="restore_status", classes="field_label")

                with Horizontal(id="restore_buttons"):
                    yield Button("Restore", id="btn_restore", variant="success")
                    yield Button("Delete Backup", id="btn_delete", variant="error")
                    yield Button("Cancel", id="btn_cancel")

    def on_mount(self) -> None:
        self._load_backups()
        try:
            self.set_focus(self.query_one("#backup_list", ListView))
        except Exception:
            pass

    def _load_backups(self) -> None:
        """Load available backups from ~/.bedrux/backups."""
        self._backups = list_backups()
        self._render_backup_list()

    def _render_backup_list(self) -> None:
        lv = self.query_one("#backup_list", ListView)
        lv.clear()

        if not self._backups:
            lv.append(ListItem(Label("No backups found")))
        else:
            for backup in self._backups:
                lv.append(ListItem(Label(backup.display_name)))

        if self._backups:
            lv.index = 0

    def _selected_backup(self) -> BackupInfo | None:
        if not self._backups:
            return None
        lv = self.query_one("#backup_list", ListView)
        idx = lv.index
        if idx is None or idx < 0 or idx >= len(self._backups):
            return None
        return self._backups[idx]

    def _set_status(self, message: str) -> None:
        try:
            self.query_one("#restore_status", Static).update(message)
        except Exception:
            pass

    def action_back(self) -> None:
        if self._is_restoring:
            return
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self._load_backups()
        self._set_status("Backup list refreshed.")

    def action_restore(self) -> None:
        if self._is_restoring:
            return
        self.run_worker(self._run_restore(), exclusive=True)

    def action_delete_backup(self) -> None:
        if self._is_restoring:
            return
        self.run_worker(self._run_delete(), exclusive=True)

    async def _run_delete(self) -> None:
        backup = self._selected_backup()
        if not backup:
            self._set_status("No backup selected.")
            return

        self._set_status(f"Deleting {backup.path.name}...")

        try:
            success = await asyncio.to_thread(delete_backup, backup.path)
            if success:
                self._set_status(f"Deleted: {backup.path.name}")
                self._load_backups()
            else:
                self._set_status("Failed to delete backup.")
        except Exception as e:
            self._set_status(f"Error: {e}")

    async def _run_restore(self) -> None:
        backup = self._selected_backup()
        if not backup:
            self._set_status("No backup selected.")
            return

        self._is_restoring = True

        # Disable buttons
        try:
            self.query_one("#btn_restore", Button).disabled = True
            self.query_one("#btn_delete", Button).disabled = True
            self.query_one("#btn_cancel", Button).disabled = True
        except Exception:
            pass

        new_name = self.query_one("#new_name", Input).value.strip() or None

        # Validate new name if provided
        if new_name:
            valid, error = validate_instance_name(new_name)
            if not valid:
                self._set_status(f"Error: {error}")
                self._is_restoring = False
                self._enable_buttons()
                return

        self._set_status(f"[+] Restoring {backup.path.name}...")

        try:
            instances_dir = get_bedrux_home() / "instances"

            restored_path = await asyncio.to_thread(
                restore_backup,
                backup.path,
                instances_dir,
                new_name=new_name,
            )

            # Add to installations list
            instance_name = restored_path.name
            server_cmd = get_server_command()

            new_installation = Installation(
                name=instance_name,
                path=str(restored_path),
                server_cmd=server_cmd,
            )

            merged = list(self._existing)
            existing_paths = {str(i.resolved_path()) for i in merged}
            if str(new_installation.resolved_path()) not in existing_paths:
                merged.append(new_installation)

            self._store.save(merged)

            self._set_status(f"[✓] Restored as '{instance_name}'!")

            # Wait a moment so user sees success
            await asyncio.sleep(1.5)

            self._is_restoring = False
            self.app.pop_screen()
            self._on_done()

        except Exception as e:
            self._set_status(f"Error: {e}")
            self._is_restoring = False
            self._enable_buttons()

    def _enable_buttons(self) -> None:
        try:
            self.query_one("#btn_restore", Button).disabled = False
            self.query_one("#btn_delete", Button).disabled = False
            self.query_one("#btn_cancel", Button).disabled = False
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "btn_restore":
                self.action_restore()
            case "btn_delete":
                self.action_delete_backup()
            case "btn_cancel":
                self.action_back()
