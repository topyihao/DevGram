# DevGram — 中文快速指南（简体）

[![English](https://img.shields.io/badge/README-English-blue)](README.md)

把 Telegram 变成你的开发终端：创建项目、执行 Shell 命令，并驱动 tmux 里的编码代理（如 Codex/Claude Code）。

## 快速开始

前置条件
- Python 3.10+，tmux（`sudo apt install tmux` 或 `brew install tmux`）
- 从 @BotFather 获取 Telegram 机器人 Token

安装
- `python -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`

配置
- 复制 `.env.example` 为 `.env` 并填写：
  - `TELEGRAM_BOT_TOKEN` 机器人 Token
  - `TELEGRAM_ALLOWED_USER_IDS` 允许访问的 Telegram 数字 ID（逗号分隔）
  - 可选：`WORKSPACE_DIR`、`PROJECTS_DIR`、`TMUX_CODEX_CMD`（默认 `codex`）

运行
- `python -m bot.bot`

## 常用命令
- `/mode shell|term` — 选择普通消息处理模式
- `/status` — 显示当前模式 / 工作目录 / tmux 目标
- `/proj` — 列出所有项目（附带深链）
- `/new "名称"` — 创建项目，启动 tmux + 代理，并返回深链
- `/open <slug>` — 将当前聊天绑定到项目（设置 cwd + term 目标）
- `/rm <slug>` — 删除项目（带确认）
- `/sh <cmd>` — 执行 Shell 命令（支持 `cd`、`source`、`export`、`unset`）
- `/cwd`、`/env`、`/reset`
- `/term_status`、`/term_send <文本>`、`/term_capture`

## 说明
- `/new` 会在项目目录创建 `.venv`，在 tmux 会话中激活，并启动你的代理命令；首次输出（如审批提示）会被捕获并发送到聊天。
- 终端模式：先回复 “Working...”，完成后将同一条消息编辑为最终结果；若过大则以文件发送。

## 安全
- 用 `TELEGRAM_ALLOWED_USER_IDS` 做访问控制；建议在低权限用户/容器下运行，并将 `WORKSPACE_DIR` 限定到安全目录。
