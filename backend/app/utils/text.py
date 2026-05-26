from __future__ import annotations

import re
import unicodedata


WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower().strip()
    normalized = WHITESPACE_RE.sub(" ", normalized)
    return normalized

