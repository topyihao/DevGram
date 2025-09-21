from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Optional, Tuple


TELEGRAM_MAX = 4000


def redact_env_value(key: str, value: str) -> str:
    k = key.lower()
    if any(s in k for s in ("secret", "token", "key", "password", "passwd")):
        if not value:
            return value
        if len(value) <= 8:
            return "*" * len(value)
        return value[:2] + "*" * (len(value) - 4) + value[-2:]
    return value


def chunk_text(text: str, limit: int = TELEGRAM_MAX) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + limit)
        chunks.append(text[start:end])
        start = end
    return chunks


CODE_BLOCK_RE = re.compile(r"```(\w+)?\n([\s\S]*?)```", re.MULTILINE)


@dataclass
class CodeBlock:
    lang: Optional[str]
    code: str


def extract_code_block(text: str) -> Optional[CodeBlock]:
    m = CODE_BLOCK_RE.search(text)
    if not m:
        return None
    lang = (m.group(1) or "").strip().lower() or None
    code = m.group(2)
    return CodeBlock(lang=lang, code=code)

