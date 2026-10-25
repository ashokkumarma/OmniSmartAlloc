"""Guard that only lets single, read-only Lightning SQL statements through."""
from __future__ import annotations

import re

ALLOWED_FIRST = {"SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN"}
FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|CACHE|UNCACHE|REFRESH|"
    r"REGISTER|COMPILE|EXPORT|UPSERT)\b",
    re.I,
)
_STRINGS = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`[^`]*`")
_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)


class ReadOnlyViolation(ValueError):
    pass


def ensure_read_only(sql: str) -> str:
    code = _STRINGS.sub("''", _COMMENTS.sub(" ", sql)).strip().rstrip(";").strip()
    if not code:
        raise ReadOnlyViolation("empty statement")
    if ";" in code:
        raise ReadOnlyViolation("only one statement per call is allowed")
    first = code.split(None, 1)[0].upper()
    if first not in ALLOWED_FIRST:
        raise ReadOnlyViolation(f"'{first}' is not allowed; use SELECT/SHOW/DESCRIBE/EXPLAIN")
    if m := FORBIDDEN.search(code):
        raise ReadOnlyViolation(f"keyword '{m.group(1).upper()}' is not allowed in read-only mode")
    return sql.strip().rstrip(";").strip()
