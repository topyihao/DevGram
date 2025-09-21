from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from typing import Optional, Tuple


def _tmux_exists() -> bool:
    return shutil.which("tmux") is not None


async def _run_tmux(*args: str, timeout: int = 10) -> Tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "tmux",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return 124, "", f"tmux timeout after {timeout}s"
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


def _increment(prev: str, new: str) -> str:
    if not prev:
        return new
    # Find the longest suffix of prev that is a prefix of new
    max_overlap = min(len(prev), len(new))
    start = 0
    # Optimize by checking a window near the end of prev
    # simple rolling overlap
    for k in range(max_overlap, 0, -1):
        if prev[-k:] == new[:k]:
            start = k
            break
    return new[start:]


@dataclass
class TmuxResult:
    snapshot: str
    increment: str


class TmuxBridge:
    def __init__(self, target: str, capture_lines: int = 1200):
        self.target = target
        self.capture_lines = capture_lines

    async def capture(self) -> str:
        # -p print, -J join wrapped lines, -S -N from N lines before bottom
        rc, out, err = await _run_tmux(
            "capture-pane", "-p", "-J", "-t", self.target, "-S", f"-{self.capture_lines}",
            timeout=10,
        )
        if rc != 0:
            raise RuntimeError(f"tmux capture-pane failed: {err.strip() or rc}")
        return out

    async def send_keys(self, text: str, send_enter: bool = True) -> None:
        # Send each line; end with Enter to submit
        for part in text.splitlines():
            rc, _, err = await _run_tmux("send-keys", "-t", self.target, part, timeout=10)
            if rc != 0:
                raise RuntimeError(f"tmux send-keys failed: {err.strip() or rc}")
            # Add literal newline within the app if multi-line message
            rc, _, err = await _run_tmux("send-keys", "-t", self.target, "C-j", timeout=10)
            if rc != 0:
                raise RuntimeError(f"tmux send-keys newline failed: {err.strip() or rc}")
        if send_enter:
            rc, _, err = await _run_tmux("send-keys", "-t", self.target, "Enter", timeout=10)
            if rc != 0:
                raise RuntimeError(f"tmux send-keys Enter failed: {err.strip() or rc}")

    async def send_and_capture(self, text: str, *, prev_snapshot: str = "", timeout_seconds: int = 20) -> TmuxResult:
        # Initialize snapshot if missing
        if not prev_snapshot:
            try:
                prev_snapshot = await self.capture()
            except Exception:
                prev_snapshot = ""

        await self.send_keys(text, send_enter=True)

        # Poll until output stabilizes or timeout
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        last = await self.capture()
        stable_count = 0
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.35)
            cur = await self.capture()
            if cur == last:
                stable_count += 1
                if stable_count >= 2:  # ~700ms unchanged
                    break
            else:
                last = cur
                stable_count = 0

        increment = _increment(prev_snapshot, last)
        return TmuxResult(snapshot=last, increment=increment)

    @staticmethod
    def _looks_working(text: str) -> bool:
        # Heuristic for Codex/Claude terminals: a line like "Working (Xs • Esc to interrupt)"
        t = text.lower()
        if "esc to interrupt" in t:
            return True
        if "working (" in t:
            return True
        return False

    async def send_and_wait_idle(self, text: str, *, prev_snapshot: str = "", timeout_seconds: int = 60) -> TmuxResult:
        # Initialize snapshot if missing
        if not prev_snapshot:
            try:
                prev_snapshot = await self.capture()
            except Exception:
                prev_snapshot = ""

        await self.send_keys(text, send_enter=True)

        deadline = asyncio.get_event_loop().time() + timeout_seconds
        last = await self.capture()
        stable_count = 0

        # Wait for terminal to become idle: content stable and no "Working"/"Esc to interrupt"
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.5)
            cur = await self.capture()

            if cur == last:
                if not self._looks_working(cur):
                    stable_count += 1
                else:
                    stable_count = 0
            else:
                last = cur
                stable_count = 0

            if stable_count >= 3:  # ~1.5s idle
                break

        increment = _increment(prev_snapshot, last)
        return TmuxResult(snapshot=last, increment=increment)

    @staticmethod
    def available() -> bool:
        return _tmux_exists()
