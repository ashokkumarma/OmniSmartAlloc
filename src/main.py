"""CLI: python -m src.main "your question across fragmented sources" """
from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path

from src.agent import ReActAgent
from src.agent.react import Step
from src.config import MissingSetting, get_settings
from src.data_connectors.zetaris_jdbc import ZetarisJdbcConnector
from src.llm import build_llm
from src.prompts import OMNISMARTALLOC_SYSTEM_PROMPT, TRACK1_SYSTEM_PROMPT
from src.tools import ToolRegistry, build_discovery_tools
from src.allocation.held import used_since
from src.tools.allocation_tools import build_allocation_tools

PROMPTS = {"generic": TRACK1_SYSTEM_PROMPT, "omnismartalloc": OMNISMARTALLOC_SYSTEM_PROMPT}
OUTBOX_DIR = Path(__file__).resolve().parent.parent / "demo" / "outbox"
EVENT_PREFIX = "@@step "


def describe_step(step: Step) -> str:
    """One plain-English line per tool call, for the live trace in the ops UI."""
    try:
        a = json.loads(step.arguments or "{}")
    except json.JSONDecodeError:
        a = {}
    sku = a.get("sku", "")
    return {
        "list_sources": "Discovered the data sources registered in Zetaris",
        "list_tables": f"Listed tables in {a.get('source', '?')}",
        "describe_table": f"Read the columns of {a.get('source', '?')}.{a.get('table', '?')}",
        "run_query": f"Queried: {(a.get('reason') or a.get('sql') or '').strip()[:140]}",
        "compute_allocation": f"Pulled fresh data and computed the allocation for {sku}",
        "set_channel_allocation": f"Applied the allocation for {sku}",
        "create_alert": f"Raised an alert for {sku}: {a.get('problem', '')[:100]}",
        "log_decision": f"Logged the decision record for {sku}",
    }.get(step.tool, step.tool)


def _error_text(result: str) -> str:
    try:
        return str(json.loads(result).get("error", result))[:200]
    except (json.JSONDecodeError, AttributeError):
        return result[:200]


def print_event(n: int, step: Step, sources: set[str]) -> None:
    print(EVENT_PREFIX + json.dumps({"n": n, "tool": step.tool, "ok": step.ok, "sources": sorted(sources),
                                     "text": describe_step(step), "error": None if step.ok else _error_text(step.result)}),
          flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Track 1 fragmented-intelligence agent (Nemotron + Zetaris)")
    ap.add_argument("question")
    ap.add_argument("--prompt", choices=sorted(PROMPTS), default="omnismartalloc")
    ap.add_argument("--max-steps", type=int, default=None, help="override AGENT_MAX_STEPS")
    ap.add_argument("--show-trace", action="store_true")
    ap.add_argument("--events", action="store_true", help="print one JSON line per step (used by the ops UI)")
    args = ap.parse_args()

    s = get_settings()
    try:
        llm = build_llm(s)
        db = ZetarisJdbcConnector(s)
    except MissingSetting as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2
    try:
        agent = ReActAgent(llm.client, llm.model,
                           ToolRegistry(build_discovery_tools(db, s.agent_max_rows, build_allocation_tools(db, OUTBOX_DIR, used_since,
                                                                                         {"llm_provider": llm.provider, "llm_model": llm.model}))),
                           PROMPTS[args.prompt], args.max_steps or s.agent_max_steps,
                           chat_extra_headers=llm.chat_extra_headers)
        steps = 0

        def on_step(step: Step, sources: set[str]) -> None:
            nonlocal steps
            steps += 1
            print_event(steps, step, sources)

        result = agent.run(args.question, on_step=on_step if args.events else None)
    finally:
        db.close()

    if args.show_trace:
        for i, step in enumerate(result.steps, 1):
            print(f"[{i}] {step.tool}({step.arguments}) -> {'ok' if step.ok else 'error'}: {step.result[:300]}")
    print(result.answer)
    print(f"\nSources touched: {', '.join(sorted(result.sources_touched)) or 'none'}  ({result.stopped_reason})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
