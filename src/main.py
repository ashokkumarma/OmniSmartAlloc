"""CLI: python -m src.main "your question across fragmented sources" """
from __future__ import annotations

import argparse
import sys

from pathlib import Path

from src.agent import ReActAgent
from src.config import MissingSetting, get_settings
from src.data_connectors.zetaris_jdbc import ZetarisJdbcConnector
from src.llm import build_llm
from src.prompts import OMNISMARTALLOC_SYSTEM_PROMPT, TRACK1_SYSTEM_PROMPT
from src.tools import ToolRegistry, build_discovery_tools
from src.tools.allocation_tools import build_allocation_tools

PROMPTS = {"generic": TRACK1_SYSTEM_PROMPT, "omnismartalloc": OMNISMARTALLOC_SYSTEM_PROMPT}
OUTBOX_DIR = Path(__file__).resolve().parent.parent / "demo" / "outbox"


def main() -> int:
    ap = argparse.ArgumentParser(description="Track 1 fragmented-intelligence agent (Nemotron + Zetaris)")
    ap.add_argument("question")
    ap.add_argument("--prompt", choices=sorted(PROMPTS), default="omnismartalloc")
    ap.add_argument("--max-steps", type=int, default=None, help="override AGENT_MAX_STEPS")
    ap.add_argument("--show-trace", action="store_true")
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
                           ToolRegistry(build_discovery_tools(db, s.agent_max_rows, build_allocation_tools(db, OUTBOX_DIR))),
                           PROMPTS[args.prompt], args.max_steps or s.agent_max_steps,
                           chat_extra_headers=llm.chat_extra_headers)
        result = agent.run(args.question)
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
