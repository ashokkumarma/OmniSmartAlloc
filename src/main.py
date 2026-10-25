"""CLI: python -m src.main "your question across fragmented sources" """
from __future__ import annotations

import argparse
import sys

from src.agent import ReActAgent
from src.config import MissingSetting, get_settings
from src.data_connectors.zetaris_jdbc import ZetarisJdbcConnector
from src.llm import build_llm
from src.prompts import TRACK1_SYSTEM_PROMPT
from src.tools import ToolRegistry, build_discovery_tools


def main() -> int:
    ap = argparse.ArgumentParser(description="Track 1 fragmented-intelligence agent (Nemotron + Zetaris)")
    ap.add_argument("question")
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
        agent = ReActAgent(llm.client, llm.model, ToolRegistry(build_discovery_tools(db, s.agent_max_rows)),
                           TRACK1_SYSTEM_PROMPT, s.agent_max_steps, chat_extra_headers=llm.chat_extra_headers)
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
