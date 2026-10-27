"""The live trace: on_step fires once per tool call, and --events prints one parseable line per step."""
from __future__ import annotations

import json

from src.agent import ReActAgent
from src.main import EVENT_PREFIX, print_event
from src.prompts import TRACK1_SYSTEM_PROMPT
from src.tools import ToolRegistry, build_discovery_tools
from tests.conftest import ScriptedClient, completion, tool_call

JOIN_SQL = ("SELECT c.name FROM crm_pg.customers c JOIN tickets_files.tickets t ON c.customer_id = t.customer_id")


def test_on_step_reports_each_tool_call_with_its_sources(fake_db):
    client = ScriptedClient([
        completion(tool_calls=[tool_call("list_sources", {}, "c1")]),
        completion(tool_calls=[tool_call("run_query", {"sql": JOIN_SQL, "reason": "link CRM to tickets"}, "c2"),
                               tool_call("run_query", {"sql": "DROP TABLE crm_pg.customers"}, "c3")]),
        completion(content="done"),
    ])
    seen: list[tuple[str, bool, set[str]]] = []
    agent = ReActAgent(client, "fake", ToolRegistry(build_discovery_tools(fake_db)), TRACK1_SYSTEM_PROMPT, 8)
    result = agent.run("q", on_step=lambda step, sources: seen.append((step.tool, step.ok, sources)))

    assert seen == [("list_sources", True, set()),
                    ("run_query", True, {"crm_pg", "tickets_files"}),
                    ("run_query", False, set())]
    assert result.answer == "done"


def test_event_line_is_prefixed_json(fake_db, capsys):
    client = ScriptedClient([
        completion(tool_calls=[tool_call("run_query", {"sql": JOIN_SQL, "reason": "link CRM to tickets"}, "c1")]),
        completion(content="done"),
    ])
    agent = ReActAgent(client, "fake", ToolRegistry(build_discovery_tools(fake_db)), TRACK1_SYSTEM_PROMPT, 8)
    agent.run("q", on_step=lambda step, sources: print_event(1, step, sources))

    line = capsys.readouterr().out.strip()
    assert line.startswith(EVENT_PREFIX)
    event = json.loads(line[len(EVENT_PREFIX):])
    assert event == {"n": 1, "tool": "run_query", "ok": True, "sources": ["crm_pg", "tickets_files"],
                     "text": "Queried: link CRM to tickets", "error": None}


def test_failed_step_event_carries_the_plain_error_message(capsys):
    from src.agent.react import Step
    print_event(5, Step("set_channel_allocation", '{"sku": "LAMP-002"}', False, '{"error": "25% change limit"}'), set())
    event = json.loads(capsys.readouterr().out.strip()[len(EVENT_PREFIX):])
    assert event["ok"] is False and event["error"] == "25% change limit"
    assert event["text"] == "Applied the allocation for LAMP-002"
