"""Track 1 tools: discover fragmented sources in Zetaris, inspect them, and query across them.

Commands follow the Zetaris Lightning command reference:
SHOW DATASOURCES / SHOW LIGHTNING DATABASES, SHOW DATASOURCE TABLES / SHOW LIGHTNING TABLES,
DESCRIBE DATASOURCE TABLE, and read-only SELECT.
"""
from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from src.data_connectors.base import SqlConnector
from src.tools.registry import Tool

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(v: str) -> str:
    if not _IDENT.match(v):
        raise ValueError(f"invalid identifier '{v}'")
    return v


Ident = Annotated[str, AfterValidator(_ident)]


class NoArgs(BaseModel):
    pass


class ListTablesArgs(BaseModel):
    source: Ident = Field(description="Datasource or Lightning database name from list_sources")
    kind: Literal["datasource", "lightning"] = Field(description="'datasource' for external DB connections, 'lightning' for file/REST sources")


class DescribeTableArgs(BaseModel):
    source: Ident = Field(description="Datasource or Lightning database name")
    table: Ident = Field(description="Table name within the source")


class QueryArgs(BaseModel):
    sql: str = Field(description="ONE read-only SELECT statement. May join tables from different sources as <source>.<table>.")
    reason: str = Field(default="", description="Why this query answers part of the question")


def build_discovery_tools(db: SqlConnector, max_rows: int = 50) -> list[Tool]:
    def list_sources(_: NoArgs):
        return {"datasources": db.query("SHOW DATASOURCES", max_rows),
                "lightning_databases": db.query("SHOW LIGHTNING DATABASES", max_rows)}

    def list_tables(a: ListTablesArgs):
        sql = f"SHOW DATASOURCE TABLES {a.source}" if a.kind == "datasource" else f"SHOW LIGHTNING TABLES {a.source}"
        return {"source": a.source, "tables": db.query(sql, max_rows)}

    def describe_table(a: DescribeTableArgs):
        return {"table": f"{a.source}.{a.table}", "columns": db.query(f"DESCRIBE DATASOURCE TABLE {a.source}.{a.table}", 500)}

    def run_query(a: QueryArgs):
        rows = db.query(a.sql, max_rows)
        return {"row_count": len(rows), "max_rows": max_rows, "rows": rows}

    return [
        Tool("list_sources", "List every data source registered in Zetaris (external datasources and Lightning file/REST databases). Call first.", NoArgs, list_sources),
        Tool("list_tables", "List tables inside one source.", ListTablesArgs, list_tables),
        Tool("describe_table", "Show the columns and types of <source>.<table> to find join keys across sources.", DescribeTableArgs, describe_table),
        Tool("run_query", "Run one read-only SELECT (Lightning SQL). Use it to join entities across sources.", QueryArgs, run_query),
    ]
