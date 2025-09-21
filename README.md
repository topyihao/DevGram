DevGram — Develop Anywhere From Your Phone

Turn your Telegram chat into a developer terminal. Create projects, run shell commands, and drive a tmux pane running your coding agent (e.g., Codex/Claude Code) — all from your phone.

What you can do

- Run shell commands in a persistent per-chat session (with `cd`, `source`, env persistence).
- Drive a live tmux pane (term mode) that runs your Codex/Claude Code terminal.

The goal is to mimic a developer terminal over Telegram and optionally drive your existing Codex/Claude Code terminal running in tmux.

Security note: This bot can execute arbitrary commands. Restrict access via `TELEGRAM_ALLOWED_USER_IDS` and optionally run it in a sandboxed environment (container/vm) and scoped workspace.

Quick Start

1) Prerequisites

- Python 3.10+
- tmux (for term mode): `brew install tmux` (macOS) or your distro’s package
- A Telegram Bot token from @BotFather

2) Install dependencies

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3) Configure environment

Copy `.env.example` to `.env` and fill in values:

- `TELEGRAM_BOT_TOKEN`: Telegram Bot API token
- `TELEGRAM_ALLOWED_USER_IDS`: comma-separated Telegram numeric user IDs (required)
- `WORKSPACE_DIR`: path constrained for shell sessions (default: current repo)
- `PROJECTS_DIR`: root folder where new projects are created
- `TMUX_CAPTURE_LINES`, `TMUX_TIMEOUT_SECONDS`: term mode tuning

4) Run the bot

```
python -m bot.bot
```

Usage Walkthrough

1) Start a chat with your bot in Telegram, send `/start`.

2) Access is limited by `TELEGRAM_ALLOWED_USER_IDS` (no in-chat login).

3) Choose a mode for plain messages with `/mode`:
- `shell` — run shell commands with persistent cwd/env
- `term` — send to a bound tmux pane (your Codex/Claude terminal)

4) Example flows
- Shell: `/mode shell`, then `cd app && ls -la`, `source .env`, `export DEBUG=1`
- Term: create a project (below), open the deep link, then `/mode term` and send instructions

Commands

- `/start` — Welcome + usage summary
- `/help` — Detailed help
- `/mode shell|term` — Set how plain messages are interpreted
- `/status` — Show current mode, cwd, and tmux target
- `/proj` — List projects with deep links
- `/new "Name"` — Create a project, start tmux + agent, return a deep link
- `/open <slug>` — Bind this chat to a project (sets cwd + term target)
- `/rm <slug>` — Delete a project (asks for confirmation)
  - You must pass the exact slug shown by `/proj` (safety check).
- `/sh <cmd>` — Run a shell command (per-chat cwd + env). Supports:
  - `cd <path>` — change directory (limited to workspace)
  - `source <file>` — apply env from a shell script (persisted for session)
  - `. <file>` — alias for `source`
- `/cwd` — Show current working directory for your session
- `/env` — Show current env (redacts secrets)
- `/reset` — Reset shell env/cwd to defaults
- `/term_status` — Show current tmux target and capture settings
- `/term_send <text>` — Send text to the bound tmux pane and capture output
- `/term_capture` — Fetch the latest tmux pane tail without sending

Project defaults
- On `/newproject`, the bot creates a Python virtualenv `.venv` in the project folder, activates it in the tmux session, and starts your agent command.
- Set `TMUX_CODEX_CMD` in `.env` (default `codex`), e.g., `codex` or `claude code` (or an activation + cmd chain).
- The initial terminal output (first‑run approvals, etc.) is captured and sent to the chat so you can respond.
  

Message routing

- Plain messages follow the current `/mode`.
- Triple-backtick code blocks are detected:
  - ```bash ...``` or ```sh ...``` → shell
  - Otherwise falls back to current mode

Persistence

- Each chat has an in-memory session (cwd + env) and term target + snapshot.
- Optional JSON persistence in `data/` is implemented for simplicity.

Safety recommendations

- Run on a locked-down machine or container.
- Use a dedicated Unix user with minimal privileges.
- Set `WORKSPACE_DIR` to a safe project folder.
- Keep `TELEGRAM_ALLOWED_USER_IDS` strict.

Development notes

- The bot uses `python-telegram-bot` for polling and tmux for term mode.

Term Mode (tmux + Coding Agent)

Step-by-step

1) Start or identify a pane running your Codex/Claude Code terminal

```
tmux new -s codex
# in the new window, start your CLI (e.g., codex/claude terminal)
```

2) Switch to term mode and send (after binding a project)

```
/mode term
echo hello world
```

Projects workflow

1) Create and open a dedicated chat

```
/new "My App"
# Bot replies with a t.me deep link — tap it to open a project-specific chat
```

2) Or bind an existing chat to a project

```
/open my-app
/mode term
```

How it works
- The bot immediately acknowledges with "Working..." after you send a message.
- When done, it edits that message with the final output. If the output is too large for a single Telegram message, it edits to "Done. Output attached." and sends the output as a file.

Tuning
- `.env` `TMUX_CAPTURE_LINES=1200` — more lines if outputs are large
- `.env` `TMUX_TIMEOUT_SECONDS=20` — increase for slower responses

Concurrency
- Operations are serialized per pane to prevent interleaving when multiple chats target the same pane.

  

Troubleshooting

- PTB error about `AIORateLimiter` or Updater:
  - Ensure deps are up to date: `pip install -r requirements.txt --upgrade` (uses python-telegram-bot>=21)
- `tmux` not found:
  - Install tmux: `brew install tmux` (macOS) or `sudo apt install tmux` (Debian/Ubuntu)
- No output in term mode:
  - Increase `TMUX_CAPTURE_LINES`; some apps paint many lines.
  - Ensure your CLI echoes output on Enter; if it needs a different submit key, tell us to adjust send-keys.
- Shell mode path errors:
  - Paths are clamped within `WORKSPACE_DIR`.
 
Ubuntu/Linux Install

- Install system packages (Debian/Ubuntu):
  - `sudo apt update`
  - `sudo apt install -y python3 python3-venv python3-pip tmux git`

- Clone and set up the app:
- `git clone <your-fork-or-repo-url> devgram && cd devgram`
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`
  - `cp .env.example .env` and fill in:
    - `TELEGRAM_BOT_TOKEN`
    - `TELEGRAM_ALLOWED_USER_IDS`
    - Optionally: `WORKSPACE_DIR`, `PROJECTS_DIR`, `TMUX_CODEX_CMD`

- Run:
  - `python -m bot.bot`

- Optional systemd service (runs on boot):
- Create `/etc/systemd/system/devgram.service`:
    
    ```ini
    [Unit]
    Description=DevGram Telegram Bot
    After=network-online.target

    [Service]
    Type=simple
    User=devgram
    WorkingDirectory=/opt/devgram
    Environment="PYTHONUNBUFFERED=1"
    ExecStart=/opt/devgram/.venv/bin/python -m bot.bot
    Restart=on-failure

    [Install]
    WantedBy=multi-user.target
    ```
  - Copy the repo to `/opt/devgram` and ensure `.env` is present.
  - `sudo systemctl daemon-reload && sudo systemctl enable --now devgram`
