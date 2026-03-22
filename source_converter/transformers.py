"""Value normalizers for DSL field values.

Functions
---------
pad_time(v)         — '9:30' / '09:30' → '09:30:00'
normalize_boolean(v) — truthy strings → 'true', everything else → 'false'
strip_percent(v)    — '10%' → '10'
apply(value, name)  — dispatch by transformer name; unknown → passthrough
"""

from __future__ import annotations

import re
from typing import Callable


def pad_time(v: str) -> str:
    """Normalise a partial time string to HH:MM:SS format.

    Accepts H:MM, HH:MM, or HH:MM:SS (with any case surrounding whitespace).
    Non-matching strings are returned unchanged.
    """
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", v.strip())
    if not m:
        return v
    hh = m.group(1).zfill(2)
    mm = m.group(2)
    ss = m.group(3) if m.group(3) is not None else "00"
    return f"{hh}:{mm}:{ss}"


def normalize_boolean(v: str) -> str:
    """Return 'true' for truthy strings, 'false' for everything else.

    Truthy: 'true', 'yes', '1' (case-insensitive).
    """
    return "true" if v.strip().lower() in ("true", "yes", "1") else "false"


def strip_percent(v: str) -> str:
    """Strip a trailing '%' and surrounding whitespace.

    '10%' → '10', '10' → '10'.
    """
    return v.strip().rstrip("%").strip()


_REGISTRY: dict[str, Callable[[str], str]] = {
    "pad_time": pad_time,
    "normalize_boolean": normalize_boolean,
    "strip_percent": strip_percent,
}


def apply(value: str, name: str) -> str:
    """Apply the named transformer to *value*.

    Unknown transformer names are a no-op (passthrough).
    """
    fn = _REGISTRY.get(name)
    return fn(value) if fn is not None else value
