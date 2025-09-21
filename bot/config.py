import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Set

from dotenv import load_dotenv


def _parse_allowed_users(raw: Optional[str]) -> Set[int]:
    if not raw:
        return set()
    result: Set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.add(int(part))
        except ValueError:
            pass
    return result


@dataclass
class Settings:
    telegram_bot_token: str
    allowed_user_ids: Set[int]
    workspace_dir: Path
    projects_dir: Path

    max_output_chars: int = 3500
    command_timeout_seconds: int = 60

    data_dir: Path = Path("data")

    # tmux bridge
    tmux_capture_lines: int = 1200
    tmux_timeout_seconds: int = 20
    tmux_codex_cmd: Optional[str] = None


def load_settings() -> Settings:
    load_dotenv(override=False)

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    allowed_users = _parse_allowed_users(os.getenv("TELEGRAM_ALLOWED_USER_IDS"))
    if not allowed_users:
        raise RuntimeError("TELEGRAM_ALLOWED_USER_IDS must include at least one ID")

    workspace = Path(os.getenv("WORKSPACE_DIR", ".")).resolve()
    projects_dir = Path(os.getenv("PROJECTS_DIR", str(workspace / "projects"))).resolve()

    # Login modes removed — allowlist only.

    max_output_chars = int(os.getenv("MAX_OUTPUT_CHARS", "3500"))
    command_timeout_seconds = int(os.getenv("COMMAND_TIMEOUT_SECONDS", "60"))

    data_dir = Path("data").resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    tmux_capture_lines = int(os.getenv("TMUX_CAPTURE_LINES", "1200"))
    tmux_timeout_seconds = int(os.getenv("TMUX_TIMEOUT_SECONDS", "20"))
    tmux_codex_cmd = os.getenv("TMUX_CODEX_CMD") or None

    return Settings(
        telegram_bot_token=token,
        allowed_user_ids=allowed_users,
        workspace_dir=workspace,
        projects_dir=projects_dir,
        max_output_chars=max_output_chars,
        command_timeout_seconds=command_timeout_seconds,
        data_dir=data_dir,
        tmux_capture_lines=tmux_capture_lines,
        tmux_timeout_seconds=tmux_timeout_seconds,
        tmux_codex_cmd=tmux_codex_cmd,
    )
