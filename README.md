# DevGram — Develop Anywhere From Your Phone

Turn your Telegram chat into a developer terminal. Create projects, run shell commands, and drive a tmux pane running your coding agent (e.g., Codex/Claude Code) — all from your phone.

## What You Can Do

- Run shell commands in a persistent per-chat session (with `cd`, `source`, env persistence).
- Drive a tmux pane (term mode) that runs your Codex/Claude Code terminal.

The goal is to mimic a developer terminal over Telegram and optionally drive your existing Codex/Claude Code terminal running in tmux.

### Security Note
This bot can execute arbitrary commands. Restrict access via `TELEGRAM_ALLOWED_USER_IDS` and run it under a locked‑down user or container. Set `WORKSPACE_DIR` to a safe project root.

## Quick Start

### Prerequisites

- Python 3.10+
- tmux (for term mode): `brew install tmux` (macOS) or your distro’s package
- A Telegram Bot token from @BotFather

### Install

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

Copy `.env.example` to `.env` and fill in values:

- `TELEGRAM_BOT_TOKEN`: Telegram Bot API token
- `TELEGRAM_ALLOWED_USER_IDS`: comma-separated Telegram numeric user IDs (required)
- `WORKSPACE_DIR`: path constrained for shell sessions (default: current repo)
- `PROJECTS_DIR`: root folder where new projects are created
- `TMUX_CAPTURE_LINES`, `TMUX_TIMEOUT_SECONDS`: term mode tuning

### Run

```
python -m bot.bot
```

## Usage Walkthrough

1) Start a chat with your bot in Telegram, send `/start`.

2) Access is limited by `TELEGRAM_ALLOWED_USER_IDS` (no in-chat login).

3) Choose a mode for plain messages with `/mode`:
- `shell` — run shell commands with persistent cwd/env
- `term` — send to a bound tmux pane (your Codex/Claude terminal)

### Examples
- Shell: `/mode shell`, then `cd app && ls -la`, `source .env`, `export DEBUG=1`
- Term: create a project (below), open the deep link, then `/mode term` and send instructions

## Commands

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

### Project Defaults
- On `/new`, the bot creates a Python virtualenv `.venv` in the project folder, activates it in the tmux session, and starts your agent command.
- Set `TMUX_CODEX_CMD` in `.env` (default `codex`), e.g., `codex` or `claude code` (or an activation + cmd chain).
- The initial terminal output (first‑run approvals, etc.) is captured and sent to the chat so you can respond.
  

## Message Routing

- Plain messages follow the current `/mode`.
- Triple-backtick code blocks are detected:
  - ```bash ...``` or ```sh ...``` → shell
  - Otherwise falls back to current mode

## Persistence

- Each chat has an in-memory session (cwd + env) and term target + snapshot.
- Optional JSON persistence in `data/` is implemented for simplicity.

## Safety & Deployment

- Run on a locked-down machine or container.
- Use a dedicated Unix user with minimal privileges.
- Set `WORKSPACE_DIR` to a safe project folder.
- Keep `TELEGRAM_ALLOWED_USER_IDS` strict.

## Development Notes

- The bot uses `python-telegram-bot` for polling and tmux for term mode.

## Term Mode (tmux + Coding Agent)

## Projects Workflow

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

### How It Works
- The bot immediately acknowledges with "Working..." after you send a message.
- When done, it edits that message with the final output. If the output is too large for a single Telegram message, it edits to "Done. Output attached." and sends the output as a file.

### Tuning
- `.env` `TMUX_CAPTURE_LINES=1200` — more lines if outputs are large
- `.env` `TMUX_TIMEOUT_SECONDS=20` — increase for slower responses

### Concurrency
- Operations are serialized per pane to prevent interleaving when multiple chats target the same pane.

  

## Troubleshooting

- PTB error about `AIORateLimiter` or Updater:
  - Ensure deps are up to date: `pip install -r requirements.txt --upgrade` (uses python-telegram-bot>=21)
- `tmux` not found:
  - Install tmux: `brew install tmux` (macOS) or `sudo apt install tmux` (Debian/Ubuntu)
- No output in term mode:
  - Increase `TMUX_CAPTURE_LINES`; some apps paint many lines.
  - Ensure your CLI echoes output on Enter; if it needs a different submit key, tell us to adjust send-keys.
- Shell mode path errors:
  - Paths are clamped within `WORKSPACE_DIR`.
 
## Ubuntu/Linux Install

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

### Optional systemd service (runs on boot)
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


# DevGram — 中文说明（简体）

将 Telegram 变成你的开发终端。直接在手机里：创建项目、执行 Shell 命令，并驱动 tmux 里的编码代理（如 Codex/Claude Code）。

## 你能做什么

- 持久化的 Shell 会话（支持 `cd`、`source`、`export`、`unset`）。
- “终端模式”（term）：把消息发送到绑定的 tmux 面板，驱动你的编码代理。

### 安全提示
本项目可以执行任意命令。请用 `TELEGRAM_ALLOWED_USER_IDS` 做访问控制，并在受限用户或容器中运行；将 `WORKSPACE_DIR` 限定到安全目录。

## 快速开始

### 先决条件
- Python 3.10+
- tmux（终端模式需要）：`sudo apt install tmux` / `brew install tmux`
- Telegram 机器人 Token（@BotFather 获取）

### 安装
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 配置
复制 `.env.example` 为 `.env` 并填写：
- `TELEGRAM_BOT_TOKEN` 机器人 Token
- `TELEGRAM_ALLOWED_USER_IDS` 允许访问的 Telegram 数字 ID（逗号分隔）
- `WORKSPACE_DIR` Shell 会话根目录
- `PROJECTS_DIR` 新项目根目录
- `TMUX_CAPTURE_LINES`、`TMUX_TIMEOUT_SECONDS` 终端模式参数

### 运行
```
python -m bot.bot
```

## 常用命令
- `/mode shell|term` 选择普通消息的处理模式
- `/status` 查看当前模式 / 工作目录 / tmux 目标
- `/proj` 列出所有项目（含深链）
- `/new "名称"` 创建项目，启动 tmux + 代理，并返回深链
- `/open <slug>` 将当前聊天绑定到指定项目（设置 cwd + term 目标）
- `/rm <slug>` 删除项目（带确认）
- `/sh <cmd>` 执行 Shell 命令
- `/cwd`、`/env`、`/reset`
- `/term_status`、`/term_send <文本>`、`/term_capture`

### 项目默认行为
- `/new` 会在项目目录创建 `.venv`，在 tmux 会话中自动激活，并启动你的代理命令。
- 设置 `TMUX_CODEX_CMD`（默认 `codex`；例如 `claude code`），首次启动的终端输出（如审批提示）会被捕获并发送到聊天。

## 使用流程
- 新建项目：`/new "My App"` → 点击返回的深链打开“项目专属聊天”。
- 或绑定现有聊天：`/open my-app`，然后 `/mode term`。
- 发送指令后，机器人先回复 “Working...”，完成后会将同一条消息编辑为最终结果；若过大则以文件发送。

## 故障排查
- AIORateLimiter 警告：已用 PTB 21，按 `pip install -r requirements.txt --upgrade` 更新依赖。
- 找不到 tmux：安装 `tmux`。
- term 无输出：增大 `TMUX_CAPTURE_LINES`；确认代理回车能打印输出。
- Shell 路径错误：路径被限制在 `WORKSPACE_DIR` 内；删除的项目会自动把 cwd 复位到全局工作目录。

## Ubuntu/Linux 安装（简版）
```
sudo apt update && sudo apt install -y python3 python3-venv python3-pip tmux git
git clone <your-fork-or-repo-url> devgram && cd devgram
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 填好变量
python -m bot.bot
```
# DevGram — Develop Anywhere From Your Phone

[![中文/Chinese](https://img.shields.io/badge/README-中文-blue)](README.zh-CN.md)

DevGram lets you use Telegram as your developer terminal. Create projects, run shell commands, and drive a tmux pane running your coding agent (e.g., Codex/Claude Code) — right from your phone.

## Quick Start

Prereqs
- Python 3.10+ and tmux (macOS: `brew install tmux`; Ubuntu: `sudo apt install tmux`)
- Telegram bot token from @BotFather

Install
- `python -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`

Configure
- Copy `.env.example` to `.env` and set:
  - `TELEGRAM_BOT_TOKEN` — your bot token
  - `TELEGRAM_ALLOWED_USER_IDS` — comma‑separated numeric IDs
  - Optional: `WORKSPACE_DIR`, `PROJECTS_DIR`, `TMUX_CODEX_CMD` (default `codex`)

Run
- `python -m bot.bot`

## Core Commands

- `/mode shell|term` — choose how plain messages are handled
- `/status` — show current mode, cwd, tmux target
- `/proj` — list projects with deep links
- `/new "Name"` — create project, start tmux + agent, return deep link
- `/open <slug>` — bind this chat to a project (sets cwd + term target)
- `/rm <slug>` — delete a project (asks for confirmation)
- `/sh <cmd>` — run a shell command (supports `cd`, `source`, `export`, `unset`)
- `/cwd`, `/env`, `/reset`
- `/term_status`, `/term_send <text>`, `/term_capture`

Notes
- `/new` creates a `.venv` in the project, activates it in tmux, starts your agent (`TMUX_CODEX_CMD`).
- First‑run prompts (e.g., approvals) are captured and sent to the chat.
- In term mode, the bot replies “Working…” then edits the same message with the final result (large output is attached as a file).

## Safety
- Access is allowlist‑only via `TELEGRAM_ALLOWED_USER_IDS`.
- Run under a low‑privilege user or container; clamp `WORKSPACE_DIR` to a safe path.

## Ubuntu/Linux (quick)
- `sudo apt update && sudo apt install -y python3 python3-venv python3-pip tmux git`
- `git clone <your-repo> devgram && cd devgram`
- `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- `cp .env.example .env` (fill vars) and `python -m bot.bot`
