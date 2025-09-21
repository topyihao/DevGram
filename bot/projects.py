from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .tmux_bridge import _run_tmux, TmuxBridge


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = _SLUG_RE.sub("-", s).strip("-")
    return s or "project"


@dataclass
class Project:
    slug: str
    path: Path
    session: str  # tmux session name


class ProjectsManager:
    def __init__(self, root: Path, codex_cmd: Optional[str] = None):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        # Default to 'codex' if not provided; users can override via TMUX_CODEX_CMD
        self.codex_cmd = (codex_cmd or "codex").strip()

    def list(self) -> List[Project]:
        items: List[Project] = []
        if not self.root.exists():
            return items
        for p in sorted(self.root.iterdir()):
            if p.is_dir():
                slug = p.name
                items.append(Project(slug=slug, path=p, session=self._session_name(slug)))
        return items

    def exists(self, slug: str) -> bool:
        return (self.root / slug).exists()

    def path_for(self, slug: str) -> Path:
        return self.root / slug

    def target_for(self, slug: str) -> str:
        return f"{self._session_name(slug)}:0.0"

    def _session_name(self, slug: str) -> str:
        return f"codex-{slug}"

    async def create(self, display_name: str) -> Project:
        base = slugify(display_name)
        slug = base
        i = 2
        while self.exists(slug):
            slug = f"{base}-{i}"
            i += 1
        proj_path = self.path_for(slug)
        proj_path.mkdir(parents=True, exist_ok=False)
        session = self._session_name(slug)
        # Create local Python venv (.venv)
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", "-m", "venv", ".venv",
                cwd=str(proj_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
        except Exception:
            pass
        # Create tmux session in project dir
        rc, _, err = await _run_tmux("new-session", "-d", "-s", session, "-c", str(proj_path), timeout=10)
        if rc != 0:
            # Cleanup created dir
            shutil.rmtree(proj_path, ignore_errors=True)
            raise RuntimeError(f"tmux new-session failed: {err.strip() or rc}")
        # Activate venv in the pane and start the coding agent
        bridge = TmuxBridge(self.target_for(slug))
        try:
            # Activate venv if present; ignore errors
            await bridge.send_keys("source .venv/bin/activate >/dev/null 2>&1 || true", send_enter=True)
            if self.codex_cmd:
                await bridge.send_keys(self.codex_cmd, send_enter=True)
        except Exception:
            pass
        return Project(slug=slug, path=proj_path, session=session)

    async def delete(self, slug: str) -> Tuple[bool, str]:
        p = self.path_for(slug)
        if not p.exists() or not p.is_dir():
            return False, "Project not found"
        # Kill tmux session if running
        session = self._session_name(slug)
        await _run_tmux("kill-session", "-t", session, timeout=5)
        try:
            shutil.rmtree(p)
        except Exception as e:
            return False, f"Failed to remove folder: {e}"
        return True, "Deleted"
