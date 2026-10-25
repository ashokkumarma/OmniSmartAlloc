"""Tool registry: pydantic-validated arguments, OpenAI tool schemas, safe dispatch."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

MAX_RESULT_CHARS = 6000


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable[[BaseModel], Any]

    def schema(self) -> dict[str, Any]:
        params = self.args.model_json_schema()
        params.pop("title", None)
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": params}}


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    def call(self, name: str, raw_args: str | dict | None) -> tuple[bool, str]:
        """Returns (ok, json_text). Errors are returned to the model, never raised."""
        tool = self._tools.get(name)
        if tool is None:
            return False, json.dumps({"error": f"unknown tool '{name}'", "available": list(self._tools)})
        try:
            data = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip() else (raw_args or {})
            result = tool.fn(tool.args.model_validate(data))
        except (json.JSONDecodeError, ValidationError) as e:
            return False, json.dumps({"error": f"invalid arguments: {e}"})
        except Exception as e:
            return False, json.dumps({"error": f"{type(e).__name__}: {e}"})
        text = json.dumps(result, default=str)
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + '..."[truncated]"'
        return True, text
