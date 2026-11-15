"""Keep device secrets out of UI data, snapshots and troubleshooting exports."""
from __future__ import annotations

import re
from copy import deepcopy

SENSITIVE = re.compile(r"password|passwd|authorization|token|secret|credential|api.?key|^key$|^headers$", re.I)


def redact(value):
    if isinstance(value, dict):
        return {str(k): "**REDACTED**" if SENSITIVE.search(str(k)) else redact(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(https?://)[^/\s@]+@", r"\1**REDACTED**@", value)
        value = re.sub(r"([?&](?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|token|key|secret|auth)[^=]*=)[^&\s]+", r"\1**REDACTED**", value, flags=re.I)
    return deepcopy(value)


def safe_to_restore(value):
    return value == redact(value) and "**REDACTED**" not in str(value)
