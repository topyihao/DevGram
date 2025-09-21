from __future__ import annotations

import asyncio
import os
import shlex
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _clamp_cwd(path: Path, workspace_root: Path) -> Path:
    p = path.resolve()
    if _is_within(p, workspace_root):
        return p
    return workspace_root


@dataclass
class ShellSession:
    """Per-chat shell session: cwd + env.

    - Constrains cwd to `workspace_root`.
    - Persists env across commands.
    - Intercepts `cd`, `source`/`.` and `export`/`unset` to persist state.
    """

    workspace_root: Path
    cwd: Path
    env: Dict[str, str] = field(default_factory=lambda: dict(os.environ))

    def reset(self) -> None:
        self.cwd = self.workspace_root
        # Start with host environment as a baseline; could also start empty
        self.env = dict(os.environ)

    def change_dir(self, target: str) -> Tuple[bool, str]:
        target_path = (self.cwd / target).resolve() if not target.startswith("/") else Path(target)
        new_cwd = _clamp_cwd(target_path, self.workspace_root)
        if not new_cwd.exists() or not new_cwd.is_dir():
            return False, f"No such directory: {target}"
        self.cwd = new_cwd
        return True, str(self.cwd)

    async def apply_source(self, script_path: str) -> Tuple[bool, str]:
        """Apply `source file` by running a subshell and capturing resulting env.

        This merges the subshell's post-source environment back into the session env.
        """
        # Resolve path relative to current cwd
        file_path = (self.cwd / script_path).resolve() if not script_path.startswith("/") else Path(script_path)
        if not _is_within(file_path, self.workspace_root):
            return False, "Refusing to source outside workspace"
        if not file_path.exists():
            return False, f"No such file: {script_path}"

        # Run bash, source the file, then print env as NUL-separated lines
        quoted = shlex.quote(str(file_path))
        # set -a auto-exports simple KEY=VALUE lines, making .env files easier
        cmd = (
            "bash -lc "
            + shlex.quote(f"set -a; source {quoted} >/dev/null 2>&1; set +a; env -0")
        )
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=str(self.cwd),
            env=self.env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            return False, (err.decode() or f"source failed with code {proc.returncode}")

        # env -0 gives key=value\0key=value...; update session env
        merged: Dict[str, str] = {}
        for chunk in out.split(b"\x00"):
            if not chunk:
                continue
            try:
                k, v = chunk.split(b"=", 1)
                merged[k.decode()] = v.decode()
            except Exception:
                pass
        if merged:
            self.env = merged
        return True, f"Applied: {script_path}"

    def _apply_export_or_unset(self, command: str) -> Optional[str]:
        # Persist `export KEY=VAL` and `unset KEY` locally
        stripped = command.strip()
        if stripped.startswith("export "):
            rest = stripped[len("export ") :].strip()
            if not rest:
                return "Usage: export KEY=VALUE"
            for part in shlex.split(rest):
                if "=" not in part:
                    return f"Invalid export: {part}"
                key, value = part.split("=", 1)
                self.env[key] = value
            return None
        if stripped.startswith("unset "):
            key = stripped[len("unset ") :].strip()
            if not key:
                return "Usage: unset KEY"
            self.env.pop(key, None)
            return None
        return None

    async def run(self, command: str, timeout: int = 60) -> Tuple[int, str, str]:
        # Ensure cwd exists; if not, reset to workspace root (or process cwd as last resort)
        try:
            if not self.cwd.exists() or not self.cwd.is_dir():
                self.cwd = self.workspace_root if self.workspace_root.exists() else Path.cwd()
        except Exception:
            self.cwd = self.workspace_root if self.workspace_root.exists() else Path.cwd()

        # Intercept cd/source/export/unset to persist state
        stripped = command.strip()
        if stripped.startswith("cd ") or stripped == "cd":
            if stripped == "cd":
                ok, msg = self.change_dir(str(self.workspace_root))
            else:
                arg = stripped[3:].strip()
                ok, msg = self.change_dir(arg)
            return 0 if ok else 1, msg + "\n", ""

        if stripped.startswith("source "):
            arg = stripped[len("source ") :].strip()
            ok, msg = await self.apply_source(arg)
            return 0 if ok else 1, msg + "\n", ""
        if stripped.startswith(". "):
            arg = stripped[len(". ") :].strip()
            ok, msg = await self.apply_source(arg)
            return 0 if ok else 1, msg + "\n", ""

        err = self._apply_export_or_unset(stripped)
        if err is not None:
            if err:
                return 1, "", err + "\n"
            return 0, "", ""

        # For general commands, run via bash -lc to support pipes, redirects, etc.
        bash_cmd = f"bash -lc {shlex.quote(stripped)}"
        proc = await asyncio.create_subprocess_shell(
            bash_cmd,
            cwd=str(self.cwd),
            env=self.env,
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
            return 124, "", f"[timeout after {timeout}s]\n"

        return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")
