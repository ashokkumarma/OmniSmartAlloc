from __future__ import annotations

from typing import Any, Protocol


class SqlConnector(Protocol):
    """Executes ONE read-only Lightning SQL statement and returns rows as dicts."""

    def query(self, sql: str, max_rows: int = 50) -> list[dict[str, Any]]: ...
