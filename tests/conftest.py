"""Offline fakes: a scripted OpenAI-compatible client and an in-memory SQL connector."""
from __future__ import annotations

import json
from typing import Any

import pytest
from openai.types.chat import ChatCompletion

from src.data_connectors.readonly import ensure_read_only


def tool_call(name: str, args: dict[str, Any], call_id: str) -> dict:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def completion(content: str | None = None, tool_calls: list[dict] | None = None) -> ChatCompletion:
    return ChatCompletion.model_validate({
        "id": "test", "object": "chat.completion", "created": 0, "model": "fake-nemotron",
        "choices": [{"index": 0, "finish_reason": "tool_calls" if tool_calls else "stop",
                     "message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}],
    })


class ScriptedClient:
    """Mimics client.chat.completions.create, replaying responses and recording requests."""

    def __init__(self, responses: list[ChatCompletion]):
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs: Any) -> ChatCompletion:
        self.requests.append(json.loads(json.dumps(kwargs, default=str)))
        if not self._responses:
            raise AssertionError("model called more times than scripted")
        return self._responses.pop(0)


class FakeConnector:
    """Routes SQL by prefix to canned rows; enforces the same read-only guard as the real connector."""

    def __init__(self, routes: dict[str, list[dict[str, Any]]]):
        self.routes = routes
        self.executed: list[str] = []

    def query(self, sql: str, max_rows: int = 50) -> list[dict[str, Any]]:
        stmt = ensure_read_only(sql)
        self.executed.append(stmt)
        for prefix, rows in self.routes.items():
            if stmt.upper().startswith(prefix.upper()):
                return rows[:max_rows]
        raise RuntimeError(f"no fake route for: {stmt}")


@pytest.fixture
def fake_db() -> FakeConnector:
    return FakeConnector({
        "SHOW DATASOURCES": [{"name": "crm_pg", "description": "CRM Postgres"}],
        "SHOW LIGHTNING DATABASES": [{"name": "tickets_files", "description": "Support tickets CSV"}],
        "DESCRIBE DATASOURCE TABLE crm_pg.customers": [{"col_name": "customer_id", "data_type": "int"},
                                                       {"col_name": "name", "data_type": "string"}],
        "SELECT": [{"name": "Acme", "open_tickets": "3"}],
    })
