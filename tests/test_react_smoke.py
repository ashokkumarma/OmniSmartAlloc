"""Smoke test: a 3-step ReAct run (discover -> inspect -> cross-source query -> answer), fully offline."""
from __future__ import annotations

import json

from src.agent import ReActAgent
from src.prompts import TRACK1_SYSTEM_PROMPT
from src.tools import ToolRegistry, build_discovery_tools
from tests.conftest import ScriptedClient, completion, tool_call

JOIN_SQL = ("SELECT c.name, COUNT(t.ticket_id) AS open_tickets FROM crm_pg.customers c "
            "JOIN tickets_files.tickets t ON c.customer_id = t.customer_id WHERE t.status = 'open' "
            "GROUP BY c.name LIMIT 5")


def make_agent(client, db, max_steps=8):
    return ReActAgent(client, "fake-nemotron", ToolRegistry(build_discovery_tools(db)), TRACK1_SYSTEM_PROMPT, max_steps)


def test_three_step_react_across_sources(fake_db):
    client = ScriptedClient([
        completion(tool_calls=[tool_call("list_sources", {}, "c1")]),
        completion(tool_calls=[tool_call("describe_table", {"source": "crm_pg", "table": "customers"}, "c2")]),
        completion(tool_calls=[tool_call("run_query", {"sql": JOIN_SQL, "reason": "link CRM to tickets"}, "c3")]),
        completion(content="<think>joined</think>Acme has 3 open tickets. Sources: crm_pg.customers, tickets_files.tickets"),
    ])
    result = make_agent(client, fake_db).run("Which customers have open support tickets?")

    assert [s.tool for s in result.steps] == ["list_sources", "describe_table", "run_query"]
    assert all(s.ok for s in result.steps)
    assert result.stopped_reason == "answered"
    assert result.answer.startswith("Acme has 3 open tickets") and "<think>" not in result.answer
    assert result.sources_touched == {"crm_pg", "tickets_files"}
    assert fake_db.executed == ["SHOW DATASOURCES", "SHOW LIGHTNING DATABASES",
                                "DESCRIBE DATASOURCE TABLE crm_pg.customers", JOIN_SQL]

    final_request = client.requests[-1]
    assert {t["function"]["name"] for t in final_request["tools"]} == {"list_sources", "list_tables", "describe_table", "run_query"}
    tool_msgs = [m for m in final_request["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2", "c3"]
    assert json.loads(tool_msgs[2]["content"])["rows"] == [{"name": "Acme", "open_tickets": "3"}]


def test_write_attempt_is_blocked_and_reported_to_model(fake_db):
    client = ScriptedClient([
        completion(tool_calls=[tool_call("run_query", {"sql": "DROP TABLE crm_pg.customers"}, "c1")]),
        completion(content="I cannot modify data; read-only access only."),
    ])
    result = make_agent(client, fake_db).run("Delete the customers table")

    assert len(result.steps) == 1 and not result.steps[0].ok
    assert "not allowed" in result.steps[0].result
    assert fake_db.executed == []
    assert result.sources_touched == set()


def test_invalid_identifier_and_unknown_tool_are_errors_not_crashes(fake_db):
    client = ScriptedClient([
        completion(tool_calls=[tool_call("describe_table", {"source": "crm_pg; DROP", "table": "x"}, "c1"),
                               tool_call("hack_the_planet", {}, "c2")]),
        completion(content="done"),
    ])
    result = make_agent(client, fake_db).run("q")

    assert [s.ok for s in result.steps] == [False, False]
    assert "invalid arguments" in result.steps[0].result and "unknown tool" in result.steps[1].result
    assert fake_db.executed == []


def test_step_limit_stops_the_loop(fake_db):
    client = ScriptedClient([completion(tool_calls=[tool_call("list_sources", {}, f"c{i}")]) for i in range(2)])
    result = make_agent(client, fake_db, max_steps=2).run("loop forever")

    assert result.stopped_reason == "max_steps" and len(result.steps) == 2
