"""Zetaris Lightning over JDBC (JayDeBeApi). Read-only, one statement per call."""
from __future__ import annotations

from typing import Any

from src.config import Settings
from src.data_connectors.readonly import ensure_read_only

DRIVER_CLASS = "com.zetaris.lightning.jdbc.LightningDriver"


def _py(value: Any) -> Any:
    return value if value is None or isinstance(value, (str, int, float, bool)) else str(value)


class ZetarisJdbcConnector:
    def __init__(self, s: Settings):
        s.require("zetaris_jdbc_url", "zetaris_jdbc_jar", "zetaris_username", "zetaris_password")
        self._s = s
        self._conn = None

    def _connection(self):
        if self._conn is None:
            import jaydebeapi

            self._conn = jaydebeapi.connect(DRIVER_CLASS, self._s.zetaris_jdbc_url,
                                            [self._s.zetaris_username, self._s.zetaris_password],
                                            self._s.zetaris_jdbc_jar)
        return self._conn

    def query(self, sql: str, max_rows: int = 50) -> list[dict[str, Any]]:
        stmt = ensure_read_only(sql)
        cur = self._connection().cursor()
        try:
            cur.execute(stmt)
            if not cur.description:
                return []
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, map(_py, row))) for row in cur.fetchmany(max_rows)]
        finally:
            cur.close()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
