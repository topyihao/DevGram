# Repository Guidelines

## Project Structure & Module Organization
- `bot/` — main application code
  - `bot/bot.py` Telegram handlers and routing
  - `bot/config.py` env/config loader
  - `bot/shell_session.py` per‑chat shell env/cwd
  - `bot/tmux_bridge.py` tmux send/capture utilities
  - `bot/projects.py` project manager (create/list/delete + tmux sessions)
  - `bot/utils.py` helpers (code blocks, redaction)
- `data/` runtime persistence (sessions). Git‑ignored
- `.env.example` configuration template
- `requirements.txt`, `README.md`, `AGENTS.md`

## Build, Test, and Development Commands
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m bot.bot                  # run the bot (polling)
```
- Set up config by copying `.env.example` to `.env`.

## Coding Style & Naming Conventions
- Python, 4‑space indentation, PEP 8.
- Names: `snake_case` for functions/vars/modules, `PascalCase` for classes, constants `UPPER_SNAKE`.
- Keep functions short and focused; prefer clarity over cleverness.
- Avoid inline comments except when intent is non‑obvious.

## Testing Guidelines
- No formal test suite yet; prefer `pytest` for new tests.
- Place tests under `tests/`, mirror module paths, name files `test_*.py`.
- Focus on pure pieces: `shell_session.py` and `tmux_bridge.py`.
- Example: `pytest -q` (add `pytest` to dev env as needed).

## Commit & Pull Request Guidelines
- Commits: imperative mood, concise subject, context in body if needed.
  - Example: "Add tmux per‑pane queueing to prevent interleaving"
- PRs must include:
  - What changed and why, linked issues, repro/validation steps.
  - Any config/env changes (update `.env.example` + README).
  - Screenshots/logs for UX/behavioral changes when helpful.

## Security & Configuration Tips
- Restrict access via `TELEGRAM_ALLOWED_USER_IDS`; never commit `.env`.
- Constrain execution with `WORKSPACE_DIR`; the shell runs inside this root.
- When enabling term mode, bind a dedicated tmux pane per chat to avoid cross‑talk.
- Use containers or a low‑privilege user for deployment.
