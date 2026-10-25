"""ReAct loop over OpenAI-compatible tool calling (Nemotron via NIM or Meterless)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.tools.registry import ToolRegistry

_THINK = re.compile(r"<think>.*?</think>", re.S)
_SOURCE_REF = re.compile(r"\b(?:FROM|JOIN)\s+`?([A-Za-z_][A-Za-z0-9_]*)`?\.`?[A-Za-z_][A-Za-z0-9_]*", re.I)


@dataclass
class Step:
    tool: str
    arguments: str
    ok: bool
    result: str


@dataclass
class AgentResult:
    answer: str
    steps: list[Step] = field(default_factory=list)
    sources_touched: set[str] = field(default_factory=set)
    stopped_reason: str = "answered"


def _sources_from(tool: str, args: dict[str, Any]) -> set[str]:
    if tool in ("list_tables", "describe_table") and isinstance(args.get("source"), str):
        return {args["source"]}
    if tool == "run_query" and isinstance(args.get("sql"), str):
        return set(_SOURCE_REF.findall(re.sub(r"'[^']*'", "''", args["sql"])))
    return set()


class ReActAgent:
    def __init__(self, client: Any, model: str, tools: ToolRegistry, system_prompt: str,
                 max_steps: int = 8, temperature: float = 0.0, chat_extra_headers: dict[str, str] | None = None):
        self.client, self.model, self.tools = client, model, tools
        self.system_prompt, self.max_steps, self.temperature = system_prompt, max_steps, temperature
        self.chat_extra_headers = chat_extra_headers or {}

    def run(self, question: str) -> AgentResult:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt},
                                          {"role": "user", "content": question}]
        result = AgentResult(answer="")
        for _ in range(self.max_steps):
            resp = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=self.tools.schemas(), tool_choice="auto",
                temperature=self.temperature, extra_headers=self.chat_extra_headers or None)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                result.answer = _THINK.sub("", msg.content or "").strip()
                return result
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [{"id": c.id, "type": "function",
                                             "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                            for c in msg.tool_calls]})
            for call in msg.tool_calls:
                ok, output = self.tools.call(call.function.name, call.function.arguments)
                result.steps.append(Step(call.function.name, call.function.arguments, ok, output))
                if ok:
                    try:
                        result.sources_touched |= _sources_from(call.function.name, json.loads(call.function.arguments or "{}"))
                    except json.JSONDecodeError:
                        pass
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
        result.stopped_reason = "max_steps"
        result.answer = "Stopped: reached the step limit before the model produced a final answer."
        return result
