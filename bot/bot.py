from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional

from telegram import Update, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    filters,
)

from .config import Settings, load_settings
from .shell_session import ShellSession
from .utils import CodeBlock, chunk_text, extract_code_block, redact_env_value
from .tmux_bridge import TmuxBridge, _increment
from .projects import ProjectsManager, slugify


logger = logging.getLogger(__name__)


WELCOME = (
    "Welcome to DevGram!\n\n"
    "- /mode shell|term — Set default mode for messages\n"
    "- /status — Show mode/cwd/term\n"
    "- /proj — List projects\n"
    "- /new \"Name\" — Create a project and get a deep link\n"
    "- /open <slug> — Bind this chat to a project\n"
    "- /rm <slug> — Delete a project (dangerous)\n"
    "- /sh <cmd> — Run shell (supports cd, source, export)\n"
    "- /cwd — Show current working directory\n"
    "- /env — Show current env (redacted)\n"
    "- /reset — Reset shell session\n\n"
    "Term mode: /term_status, /term_send <text>, /term_capture (bind via /open or deep link)\n\n"
    "Tip: send triple backticks with \"bash\" or \"sh\" to auto-route."
)


class Session:
    def __init__(self, chat_id: int, settings: Settings):
        self.chat_id = chat_id
        self.settings = settings
        self.mode = "shell"
        self.shell = ShellSession(workspace_root=settings.workspace_dir, cwd=settings.workspace_dir)
        # term mode state
        self.term_target: Optional[str] = None
        self.term_snapshot: str = ""

    def to_json(self) -> dict:
        return {
            "mode": self.mode,
            "cwd": str(self.shell.cwd),
            "env": self.shell.env,
            "term_target": self.term_target,
            "term_snapshot": self.term_snapshot,
        }

    @classmethod
    def from_json(cls, chat_id: int, settings: Settings, data: dict) -> "Session":
        s = cls(chat_id, settings)
        s.mode = data.get("mode", "shell")
        cwd = Path(data.get("cwd", str(settings.workspace_dir)))
        s.shell.cwd = cwd if cwd.exists() else settings.workspace_dir
        env = data.get("env") or {}
        if isinstance(env, dict):
            s.shell.env = {str(k): str(v) for k, v in env.items()}
        s.term_target = data.get("term_target") or None
        s.term_snapshot = data.get("term_snapshot") or ""
        return s


class BotApp:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions: Dict[int, Session] = {}

        self._sessions_dir = settings.data_dir / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)


        # Per-tmux-target locks to serialize access and avoid interleaving
        self._tmux_locks: Dict[str, asyncio.Lock] = {}

        # Projects manager
        self.projects = ProjectsManager(settings.projects_dir, codex_cmd=settings.tmux_codex_cmd)

    def _session_path(self, chat_id: int) -> Path:
        return self._sessions_dir / f"{chat_id}.json"

    def get_session(self, chat_id: int) -> Session:
        if chat_id in self.sessions:
            return self.sessions[chat_id]
        path = self._session_path(chat_id)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                sess = Session.from_json(chat_id, self.settings, data)
                self.sessions[chat_id] = sess
                return sess
            except Exception:
                logger.exception("Failed to load session for chat %s", chat_id)
        sess = Session(chat_id, self.settings)
        self.sessions[chat_id] = sess
        return sess

    def save_session(self, chat_id: int) -> None:
        sess = self.sessions.get(chat_id)
        if not sess:
            return
        path = self._session_path(chat_id)
        try:
            path.write_text(json.dumps(sess.to_json(), indent=2))
        except Exception:
            logger.exception("Failed to save session %s", chat_id)

    def _get_tmux_lock(self, target: str) -> asyncio.Lock:
        lock = self._tmux_locks.get(target)
        if lock is None:
            lock = asyncio.Lock()
            self._tmux_locks[target] = lock
        return lock

    def authorized(self, user_id: Optional[int]) -> bool:
        return bool(user_id) and (int(user_id) in self.settings.allowed_user_ids)

    async def _send_long_text(self, update: Update, text: str, filename_hint: str = "output.txt") -> None:
        if len(text) <= self.settings.max_output_chars:
            for chunk in chunk_text(text, limit=self.settings.max_output_chars):
                await update.effective_chat.send_message(chunk)
            return
        # Send as a file if too long
        tmp = tempfile.NamedTemporaryFile("w+", suffix=filename_hint, delete=False)
        try:
            tmp.write(text)
            tmp.flush()
            tmp.close()
            await update.effective_chat.send_document(tmp.name)
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

    async def handle_start(self, update: Update, context: CallbackContext) -> None:
        # Ensure commands are visible in the Telegram composer
        try:
            await context.bot.set_my_commands(build_bot_commands())
        except Exception:
            pass
        # Bind to project via deep-link start parameter: p_<slug>
        if context.args:
            param = (context.args[0] or "").strip()
            if param.startswith("p_"):
                slug = param[2:]
                if not slug:
                    await update.message.reply_text("Invalid project link.")
                    return
                if not self.projects.exists(slug):
                    await update.message.reply_text("Project not found. Use /proj to list.")
                    return
                sess = self.get_session(update.effective_chat.id)
                proj_path = self.settings.projects_dir / slug
                sess.shell.cwd = proj_path
                # Clamp workspace to the project dir for safety
                sess.shell.workspace_root = proj_path
                sess.term_target = self.projects.target_for(slug)
                sess.mode = "term"
                self.save_session(update.effective_chat.id)
                await update.message.reply_text(f"Bound to project '{slug}'. Mode set to term; cwd={proj_path}")
                return
        await update.message.reply_text(WELCOME)

    async def handle_help(self, update: Update, context: CallbackContext) -> None:
        await update.message.reply_text(WELCOME)

    def _deep_link(self, username: str, slug: str) -> str:
        return f"https://t.me/{username}?start=p_{slug}"

    async def handle_mode(self, update: Update, context: CallbackContext) -> None:
        sess = self.get_session(update.effective_chat.id)
        if not context.args:
            await update.message.reply_text(f"Current mode: {sess.mode}")
            return
        mode = context.args[0].lower()
        if mode not in ("shell", "term"):
            await update.message.reply_text("Usage: /mode shell|term")
            return
        sess.mode = mode
        self.save_session(update.effective_chat.id)
        await update.message.reply_text(f"Mode set to: {mode}")

    async def handle_newproject(self, update: Update, context: CallbackContext) -> None:
        name = (update.message.text or "").strip()
        if name.startswith("/newproject"):
            name = name[len("/newproject"):].strip()
        elif name.startswith("/new"):
            name = name[len("/new"):].strip()
        # Allow quoted name or bare words
        if name.startswith("\"") and name.endswith("\"") and len(name) >= 2:
            name = name[1:-1]
        if not name:
            await update.message.reply_text('Usage: /new "Project Name"')
            return
        try:
            proj = await self.projects.create(name)
        except Exception as e:
            await update.message.reply_text(f"Create failed: {e}")
            return
        # Build deep link
        me = await context.bot.get_me()
        link = self._deep_link(me.username, proj.slug)
        await update.message.reply_text(
            f"Created project '{proj.slug}' at {proj.path}\n"
            f"tmux session: {proj.session}\n"
            f"Open a dedicated chat: {link}"
        )
        # Capture initial terminal output (e.g., first-run prompts) and send to chat
        try:
            target = self.projects.target_for(proj.slug)
            bridge = TmuxBridge(target, capture_lines=self.settings.tmux_capture_lines)
            async with self._get_tmux_lock(target):
                # Wait briefly for startup output to render, then capture until stable
                last = await bridge.capture()
                for _ in range(4):
                    await asyncio.sleep(0.5)
                    cur = await bridge.capture()
                    if cur == last:
                        break
                    last = cur
            text = last.strip()
            if text:
                await self._send_long_text(update, text + "\n", filename_hint="newproject.txt")
        except Exception:
            pass

    async def handle_projects(self, update: Update, context: CallbackContext) -> None:
        me = await context.bot.get_me()
        items = self.projects.list()
        if not items:
            await update.message.reply_text("No projects. Create one with /new \"Name\".")
            return
        lines = []
        for p in items:
            lines.append(f"- {p.slug}  ({p.path})  [{self._deep_link(me.username, p.slug)}]")
        await self._send_long_text(update, "\n".join(lines) + "\n", filename_hint="projects.txt")

    async def handle_bindproject(self, update: Update, context: CallbackContext) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /open <slug>")
            return
        slug = slugify(context.args[0])
        if not self.projects.exists(slug):
            await update.message.reply_text("Project not found. Use /proj.")
            return
        sess = self.get_session(update.effective_chat.id)
        proj_path = self.settings.projects_dir / slug
        sess.shell.cwd = proj_path
        sess.shell.workspace_root = proj_path
        sess.term_target = self.projects.target_for(slug)
        sess.mode = "term"
        self.save_session(update.effective_chat.id)
        await update.message.reply_text(f"Bound to project '{slug}'. Mode set to term; cwd={proj_path}")

    async def handle_rm_request(self, update: Update, context: CallbackContext) -> None:
        # Require an explicit, exact slug to avoid accidental deletions
        if not context.args:
            await update.message.reply_text("Usage: /rm <slug> (use exact slug from /proj)")
            return
        raw = (context.args[0] or "").strip().lower()
        # Only allow already-slugified names; reject if slugify would change it
        slug = slugify(raw)
        if slug != raw:
            await update.message.reply_text("Invalid slug. Use the exact slug shown by /proj.")
            return
        if not self.projects.exists(slug):
            await update.message.reply_text("Project not found.")
            return
        kb = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(text=f"Delete {slug}", callback_data=f"rm:{slug}"),
                InlineKeyboardButton(text="Cancel", callback_data=f"cancel_rm:{slug}"),
            ]]
        )
        await update.message.reply_text(
            f"Delete project '{slug}'? This removes the folder and kills the tmux session.",
            reply_markup=kb,
        )

    async def _delete_project(self, slug: str) -> tuple[bool, str]:
        ok, msg = await self.projects.delete(slug)
        if ok:
            target = self.projects.target_for(slug)
            for s in list(self.sessions.values()):
                if s.term_target == target:
                    s.term_target = None
                    s.mode = "shell"
                    s.shell.workspace_root = self.settings.workspace_dir
                    s.shell.cwd = self.settings.workspace_dir
                    self.save_session(s.chat_id)
        return ok, msg

    async def handle_rm_callback(self, update: Update, context: CallbackContext) -> None:
        q = update.callback_query
        if not q or not q.data:
            return
        await q.answer()
        data = q.data
        chat = q.message.chat if q.message else None
        if data.startswith("rm:"):
            slug = data.split(":", 1)[1].strip().lower()
            # Double-check slug is already slugified
            if slugify(slug) != slug:
                try:
                    await q.edit_message_text("Invalid slug.")
                except Exception:
                    if chat:
                        await chat.send_message("Invalid slug.")
                return
            ok, msg = await self._delete_project(slug)
            try:
                await q.edit_message_text(msg)
            except Exception:
                if chat:
                    await chat.send_message(msg)
        elif data.startswith("cancel_rm:"):
            try:
                await q.edit_message_text("Deletion cancelled.")
            except Exception:
                if chat:
                    await chat.send_message("Deletion cancelled.")

    async def handle_status(self, update: Update, context: CallbackContext) -> None:
        sess = self.get_session(update.effective_chat.id)
        text = (
            f"mode: {sess.mode}\n"
            f"cwd: {sess.shell.cwd}\n"
            f"term: {sess.term_target or '(unset)'}\n"
        )
        await update.message.reply_text(text)

    # Chat mode removed

    async def _run_shell_text(self, update: Update, sess: Session, command: str) -> None:
        rc, out, err = await sess.shell.run(command, timeout=self.settings.command_timeout_seconds)
        text = ""
        if out:
            text += out
        if err:
            text += ("\n" if text else "") + err
        prefix = "" if rc == 0 else f"[exit {rc}]\n"
        await self._send_long_text(update, prefix + (text or "(no output)\n"), filename_hint="shell.txt")
        self.save_session(update.effective_chat.id)

    async def handle_shell(self, update: Update, context: CallbackContext) -> None:
        sess = self.get_session(update.effective_chat.id)
        text = update.message.text or ""
        # Strip command name if present
        if text.startswith("/sh"):
            text = text[len("/sh"):].strip()
        if not text:
            await update.message.reply_text("Usage: /sh <command>")
            return
        await self._run_shell_text(update, sess, text)

    # Python mode removed

    async def handle_cwd(self, update: Update, context: CallbackContext) -> None:
        sess = self.get_session(update.effective_chat.id)
        await update.message.reply_text(str(sess.shell.cwd))

    async def handle_env(self, update: Update, context: CallbackContext) -> None:
        sess = self.get_session(update.effective_chat.id)
        pairs = [f"{k}={redact_env_value(k, v)}" for k, v in sorted(sess.shell.env.items())]
        await self._send_long_text(update, "\n".join(pairs) + "\n", filename_hint="env.txt")

    async def handle_reset(self, update: Update, context: CallbackContext) -> None:
        sess = self.get_session(update.effective_chat.id)
        sess.shell.reset()
        self.save_session(update.effective_chat.id)
        await update.message.reply_text("Session reset.")

    # Login/admin features removed

    async def handle_text(self, update: Update, context: CallbackContext) -> None:
        sess = self.get_session(update.effective_chat.id)
        text = update.message.text or ""

        # Code block routing
        block = extract_code_block(text)
        if block:
            if block.lang in ("bash", "sh"):
                await self._run_shell_text(update, sess, block.code)
                return
            if block.lang in ("py", "python"):
                await update.message.reply_text("Python mode is disabled. Use /sh with python or a heredoc.")
                return

        # Mode routing
        # Ignore empty or lone slash
        if text.strip() == "" or text.strip() == "/":
            await update.message.reply_text("Use the command menu or type /help.")
            return
        if sess.mode == "shell":
            await self._run_shell_text(update, sess, text)
            return
        if sess.mode == "term":
            await self._run_term(update, sess, text)
            return
        # Default to shell
        await self._run_shell_text(update, sess, text)

    async def _run_term(self, update: Update, sess: Session, text: str) -> None:
        target = sess.term_target
        if not target:
            await update.message.reply_text("No tmux target bound. Use /open <slug> or the deep link from /new.")
            return
        if not TmuxBridge.available():
            await update.message.reply_text("tmux is not available on host.")
            return
        bridge = TmuxBridge(target, capture_lines=self.settings.tmux_capture_lines)
        try:
            async with self._get_tmux_lock(target):
                # Send an immediate acknowledgement to indicate progress
                ack_msg = None
                try:
                    ack_msg = await update.effective_chat.send_message("Working...")
                except Exception:
                    ack_msg = None

                result = await bridge.send_and_wait_idle(
                    text,
                    prev_snapshot=sess.term_snapshot,
                    timeout_seconds=max(self.settings.tmux_timeout_seconds, 30),
                )
        except Exception as e:
            await update.message.reply_text(f"tmux error: {e}")
            return
        sess.term_snapshot = result.snapshot
        inc = result.increment.strip()
        final_text = inc or "(no visible output)"
        # If short enough, edit the ack message with the final output
        if len(final_text) <= self.settings.max_output_chars:
            try:
                if ack_msg is not None:
                    await ack_msg.edit_text(final_text)
                else:
                    await self._send_long_text(update, final_text + "\n", filename_hint="term.txt")
            except Exception:
                await self._send_long_text(update, final_text + "\n", filename_hint="term.txt")
        else:
            # Too long to fit in a single message; edit ack and send as file
            try:
                if ack_msg is not None:
                    await ack_msg.edit_text("Done. Output attached.")
            except Exception:
                pass
            await self._send_long_text(update, final_text + "\n", filename_hint="term.txt")
        self.save_session(update.effective_chat.id)

    async def handle_term_status(self, update: Update, context: CallbackContext) -> None:
        sess = self.get_session(update.effective_chat.id)
        target = sess.term_target
        await update.message.reply_text(f"term target: {target or '(unset)'}; capture_lines={self.settings.tmux_capture_lines}")

    async def handle_term_send(self, update: Update, context: CallbackContext) -> None:
        text = (update.message.text or "").strip()
        if text.startswith("/term_send"):
            text = text[len("/term_send"):].strip()
        if not text:
            await update.message.reply_text("Usage: /term_send <text>")
            return
        sess = self.get_session(update.effective_chat.id)
        await self._run_term(update, sess, text)

    async def handle_term_capture(self, update: Update, context: CallbackContext) -> None:
        sess = self.get_session(update.effective_chat.id)
        target = sess.term_target
        if not target:
            await update.message.reply_text("No tmux target bound. Use /open <slug> or the deep link from /new.")
            return
        if not TmuxBridge.available():
            await update.message.reply_text("tmux is not available on host.")
            return
        bridge = TmuxBridge(target, capture_lines=self.settings.tmux_capture_lines)
        try:
            async with self._get_tmux_lock(target):
                capture = await bridge.capture()
        except Exception as e:
            await update.message.reply_text(f"tmux error: {e}")
            return
        await self._send_long_text(update, capture, filename_hint="term_capture.txt")


def require_auth(app: BotApp):
    def _wrapper(handler):
        async def inner(update: Update, context: CallbackContext):
            user = update.effective_user
            if not app.authorized(user.id if user else None):
                await update.effective_chat.send_message("Unauthorized user.")
                return
            return await handler(update, context)
        return inner
    return _wrapper


def build_bot_commands() -> list[BotCommand]:
    return [
        BotCommand("start", "Welcome"),
        BotCommand("help", "Help"),
        BotCommand("mode", "shell | term"),
        BotCommand("status", "Show mode/cwd/term"),
        BotCommand("proj", "List projects"),
        BotCommand("new", "Create project"),
        BotCommand("open", "Open project"),
        BotCommand("rm", "Remove project"),
        BotCommand("sh", "Run shell"),
        BotCommand("cwd", "Show working dir"),
        BotCommand("env", "Show env"),
        BotCommand("reset", "Reset session"),
        BotCommand("term_status", "Term status"),
        BotCommand("term_send", "Send to term"),
        BotCommand("term_capture", "Capture term tail"),
    ]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    app_state = BotApp(settings)

    # Prefer PTB's async rate limiter if available; otherwise run without it
    limiter = None
    try:
        limiter = AIORateLimiter()
    except Exception:
        logger.warning(
            "AIORateLimiter unavailable; continuing without rate limiter. Install python-telegram-bot[rate-limiter]."
        )

    async def _post_init(app: Application):
        try:
            await app.bot.set_my_commands(build_bot_commands())
        except Exception:
            pass

    builder = ApplicationBuilder().token(settings.telegram_bot_token).post_init(_post_init)
    if limiter is not None:
        builder = builder.rate_limiter(limiter)
    application: Application = builder.build()

    auth = require_auth(app_state)

    application.add_handler(CommandHandler("start", app_state.handle_start))
    application.add_handler(CommandHandler("help", app_state.handle_help))
    application.add_handler(CommandHandler("mode", auth(app_state.handle_mode)))
    # New short commands
    application.add_handler(CommandHandler("new", auth(app_state.handle_newproject)))
    application.add_handler(CommandHandler("proj", auth(app_state.handle_projects)))
    application.add_handler(CommandHandler("open", auth(app_state.handle_bindproject)))
    application.add_handler(CommandHandler("rm", auth(app_state.handle_rm_request)))
    application.add_handler(CommandHandler("status", auth(app_state.handle_status)))
    # Backwards-compatible aliases
    application.add_handler(CommandHandler("newproject", auth(app_state.handle_newproject)))
    application.add_handler(CommandHandler("projects", auth(app_state.handle_projects)))
    application.add_handler(CommandHandler("bindproject", auth(app_state.handle_bindproject)))
    application.add_handler(CommandHandler("delproject", auth(app_state.handle_rm_request)))
    
    from telegram.ext import CallbackQueryHandler
    application.add_handler(CallbackQueryHandler(auth(app_state.handle_rm_callback), pattern=r"^(rm:|cancel_rm:).+"))
    application.add_handler(CommandHandler("term_status", auth(app_state.handle_term_status)))
    application.add_handler(CommandHandler("term_send", auth(app_state.handle_term_send)))
    application.add_handler(CommandHandler("term_capture", auth(app_state.handle_term_capture)))
    application.add_handler(CommandHandler("sh", auth(app_state.handle_shell)))
    application.add_handler(CommandHandler("cwd", auth(app_state.handle_cwd)))
    application.add_handler(CommandHandler("env", auth(app_state.handle_env)))
    application.add_handler(CommandHandler("reset", auth(app_state.handle_reset)))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auth(app_state.handle_text)))

    logger.info("Starting DevGram Telegram bot...")
    application.run_polling()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
