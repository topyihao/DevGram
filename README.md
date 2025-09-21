# DevGram — Develop Anywhere From Your Phone

[English] | [中文/Chinese](README.zh-CN.md)

Turn a Telegram chat into a developer terminal. Run shell commands with a persistent per‑chat environment, or drive a tmux pane running your coding agent (e.g., Codex/Claude Code) — all from your phone.

## Quick Start

- Prereqs: Python 3.10+, tmux (for term mode), Telegram bot token (@BotFather)
- Install: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Configure: copy `.env.example` to `.env` and set at least:
  - `TELEGRAM_BOT_TOKEN` — your bot token
  - `TELEGRAM_ALLOWED_USER_IDS` — comma‑separated numeric IDs allowed to use the bot
  - Optional: `WORKSPACE_DIR`, `PROJECTS_DIR`, `TMUX_CODEX_CMD` (default `codex`), `TMUX_CAPTURE_LINES`, `TMUX_TIMEOUT_SECONDS`, `MAX_OUTPUT_CHARS`, `COMMAND_TIMEOUT_SECONDS`
- Run: `python -m bot.bot`

## Use It

- Start a chat with your bot, send `/start`.
- Choose how plain messages are handled: `/mode shell` or `/mode term`.
- Shell mode: `/sh <cmd>` or send text; supports `cd`, `source`/`.` (env merge), `export`, `unset`.
- Term mode: bind to a project’s tmux pane, then use `/term_send <text>` or `/term_capture`.
- Code blocks: messages with ```bash or ```sh are auto‑routed to shell.

## Projects (term mode)

- `/new "Name"` — creates a project under `PROJECTS_DIR`, starts a tmux session, and returns a deep‑link to a dedicated chat.
- `/open <slug>` — bind current chat to an existing project (sets cwd + tmux target, switches to term mode).
- Defaults: a `.venv` is created and activated in tmux; your agent command from `TMUX_CODEX_CMD` runs (default `codex`). First‑run output is captured and sent back.

## Core Commands

- `/mode shell|term`, `/status`
- `/proj`, `/new "Name"`, `/open <slug>`, `/rm <slug>` (danger)
- `/sh <cmd>`, `/cwd`, `/env`, `/reset`
- `/term_status`, `/term_send <text>`, `/term_capture`

## Security

- Strongly restrict access with `TELEGRAM_ALLOWED_USER_IDS`.
- Run under a low‑privilege user or container; clamp `WORKSPACE_DIR` to a safe path.
- This bot can execute arbitrary commands inside the workspace.

## Notes

- Long outputs are chunked or sent as files. Sessions persist to `data/`.
- Requirements: `python-telegram-bot>=21,<22` and `python-dotenv` (see `requirements.txt`).

