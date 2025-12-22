from __future__ import annotations

import asyncio
import os
import re
import signal
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional


LogFn = Callable[[str], None]
StatusFn = Callable[[bool], None]


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mKHF]?")


@dataclass(slots=True)
class ProcessInfo:
    pid: int


class ServerController:
    """Starts/stops the Bedrock server process and streams logs."""

    def __init__(
        self,
        *,
        server_cmd: str,
        log: LogFn,
        on_status: StatusFn,
        cwd: str | None = None,
    ) -> None:
        self._server_cmd = server_cmd
        self._log = log
        self._on_status = on_status
        self._cwd = cwd

        self._proc: Optional[asyncio.subprocess.Process] = None
        self._reader_tasks: list[asyncio.Task] = []
        self._wait_task: Optional[asyncio.Task] = None

    @property
    def process(self) -> Optional[asyncio.subprocess.Process]:
        return self._proc

    @property
    def pid(self) -> Optional[int]:
        return getattr(self._proc, "pid", None) if self._proc else None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        if self.is_running():
            self._log("Server is already running.")
            return

        if self._cwd:
            self._log(f"Working directory: {self._cwd}")
        self._log(f"Starting server: {self._server_cmd}")

        self._proc = await asyncio.create_subprocess_shell(
            self._server_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
            start_new_session=True,
            cwd=self._cwd,
        )

        self._on_status(True)
        pid = self.pid
        if pid is not None:
            self._log(f"Server started (PID={pid}).")

        self._reader_tasks = [
            asyncio.create_task(self._read_stream(self._proc.stdout)),
            asyncio.create_task(self._read_stream(self._proc.stderr)),
        ]
        self._wait_task = asyncio.create_task(self._wait_for_exit())

    async def stop(self) -> None:
        if not self._proc:
            return

        proc = self._proc
        self._log("Stopping server...")

        await self._cancel_readers()

        await self._close_stdin(proc)

        await self._terminate_process(proc)

        self._proc = None
        self._on_status(False)

    async def send_command(self, command: str) -> None:
        if not self._proc or not self._proc.stdin:
            self._log("Server is not running.")
            return

        self._proc.stdin.write((command + "\n").encode("utf-8", errors="replace"))
        await self._proc.stdin.drain()

    async def _read_stream(self, stream: Optional[asyncio.StreamReader]) -> None:
        if stream is None:
            return

        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
            cleaned = _ANSI_RE.sub("", decoded)
            self._log(cleaned)

    async def _wait_for_exit(self) -> None:
        proc = self._proc
        if not proc:
            return

        try:
            await proc.wait()
            rc = proc.returncode
            self._log(f"Server exited (code {rc}).")
        finally:
            await self._cancel_readers()
            self._proc = None
            self._on_status(False)

    async def _cancel_readers(self) -> None:
        tasks = [t for t in self._reader_tasks if not t.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._reader_tasks = []

        if self._wait_task and not self._wait_task.done():
            # Let it finish naturally; no need to cancel unless we're shutting down.
            return

    async def _close_stdin(self, proc: asyncio.subprocess.Process) -> None:
        stdin = getattr(proc, "stdin", None)
        if stdin is None:
            return
        try:
            stdin.close()
            if hasattr(stdin, "wait_closed"):
                await stdin.wait_closed()
        except Exception:
            return

    async def _terminate_process(self, proc: asyncio.subprocess.Process) -> None:
        pid = getattr(proc, "pid", None)
        if pid is None:
            return

        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            return
        except asyncio.TimeoutError:
            self._log("Server did not stop in time; force killing...")

        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except Exception:
            try:
                await proc.wait()
            except Exception:
                pass
