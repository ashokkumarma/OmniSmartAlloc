"""Run the Zetaris USL deliverable SQL files and capture every result.

    python demo/zetaris/run_usl.py                       # all files, in order
    python demo/zetaris/run_usl.py demo/zetaris/usl_queries.sql
    python demo/zetaris/run_usl.py --sql "SHOW LIGHTNING DATABASES"   # ad hoc, prints only

Statement handling:
  * lines starting with `--` are comments and are dropped;
  * a `-- @title <text>` comment labels the next statement in the results;
  * statements end at a line whose last character is `;`;
  * a `COMPILE USL ... DDL` statement keeps every following `CREATE TABLE ...;` chunk, so a multi-table
    compile is sent as ONE statement (Zetaris requires that; splitting it on `;` breaks it).

Each file's results go to demo/zetaris/results/<file stem>.json and .md. The runner never stops on an error:
it records the exact error string and carries on, so a failure is visible in the results.
Connection settings come from .env (ZETARIS_JDBC_URL / _JAR / _USERNAME / _PASSWORD); nothing is printed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402

DRIVER_CLASS = "com.zetaris.lightning.jdbc.LightningDriver"
RESULTS = HERE / "results"
DEFAULT_FILES = ["explore_channel_db.sql", "explore_amazon_api.sql", "explore_wms.sql", "explore_supplier_portal.sql",
                 "explore_channel_analytics.sql", "explore_rules_engine.sql", "usl_create.sql", "usl_queries.sql"]
MAX_ROWS = 200


def split_statements(text: str) -> list[tuple[str, str]]:
    """Return [(title, statement)] with comments removed and multi-table COMPILE USL kept whole."""
    chunks: list[tuple[str, str]] = []
    title, buf = "", []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("--"):
            if m := re.match(r"--\s*@title\s+(.*)", s):
                title = m.group(1).strip()
            continue
        if not s and not buf:
            continue
        buf.append(line.rstrip())
        if s.endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            buf = []
            if stmt:
                chunks.append((title, stmt))
            title = ""
    if tail := "\n".join(buf).strip():
        chunks.append((title, tail))
    merged: list[tuple[str, str]] = []
    for t, stmt in chunks:
        if merged and re.match(r"(?i)CREATE\s+TABLE\b", stmt) and re.match(r"(?i)COMPILE\s+USL\b", merged[-1][1]):
            merged[-1] = (merged[-1][0], merged[-1][1] + ";\n" + stmt)
        else:
            merged.append((t, stmt))
    return merged


def _py(v):
    return v if v is None or isinstance(v, (str, int, float, bool)) else str(v)


def connect():
    import jaydebeapi

    s = get_settings()
    s.require("zetaris_jdbc_url", "zetaris_jdbc_jar", "zetaris_username", "zetaris_password")
    return jaydebeapi.connect(DRIVER_CLASS, s.zetaris_jdbc_url, [s.zetaris_username, s.zetaris_password],
                              s.zetaris_jdbc_jar)


def execute(conn, stmt: str) -> dict:
    cur = conn.cursor()
    t0 = time.perf_counter()
    try:
        cur.execute(stmt)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [list(map(_py, r)) for r in cur.fetchmany(MAX_ROWS)] if cols else []
        return {"ok": True, "columns": cols, "rows": rows, "seconds": round(time.perf_counter() - t0, 2)}
    except Exception as e:  # record the exact driver error and keep going
        msg = str(e)
        if hasattr(e, "args") and e.args and hasattr(e.args[0], "getMessage"):
            msg = str(e.args[0].getMessage())
        msg = msg.split("\n\tat ")[0]  # keep the message, drop the Java stack trace
        return {"ok": False, "error": msg.strip()[:2000], "seconds": round(time.perf_counter() - t0, 2)}
    finally:
        cur.close()


def _cell(v) -> str:
    s = "" if v is None else str(v)
    s = s.replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= 160 else s[:157] + "..."


def to_markdown(name: str, results: list[dict]) -> str:
    ok = sum(r["ok"] for r in results)
    out = [f"# Results: {name}", "",
           f"Run {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} over JDBC. "
           f"{ok}/{len(results)} statements succeeded. Rows shown are capped at {MAX_ROWS}.", ""]
    for i, r in enumerate(results, 1):
        out += [f"## {i}. {r['title'] or r['sql'].splitlines()[0][:80]}", "", "```sql", r["sql"], "```", ""]
        if not r["ok"]:
            out += [f"**FAILED** ({r['seconds']}s):", "", "```text", r["error"], "```", ""]
            continue
        out.append(f"OK in {r['seconds']}s, {len(r['rows'])} row(s).")
        out.append("")
        if r["columns"]:
            out.append("| " + " | ".join(_cell(c) for c in r["columns"]) + " |")
            out.append("|" + "---|" * len(r["columns"]))
            out += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in r["rows"]]
            out.append("")
    return "\n".join(out)


def run_file(conn, path: Path) -> list[dict]:
    results = []
    for title, stmt in split_statements(path.read_text(encoding="utf-8")):
        r = execute(conn, stmt)
        r.update(title=title, sql=stmt)
        status = "OK  " if r["ok"] else "FAIL"
        detail = f"{len(r.get('rows', []))} rows" if r["ok"] else r["error"].splitlines()[0][:160]
        print(f"[{status}] {path.name}: {(title or stmt.splitlines()[0])[:70]} -> {detail}")
        results.append(r)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{path.stem}.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (RESULTS / f"{path.stem}.md").write_text(to_markdown(path.name, results), encoding="utf-8")
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--sql", help="run one ad hoc statement and print the result (nothing is written)")
    args = ap.parse_args()
    conn = connect()
    try:
        if args.sql:
            print(json.dumps(execute(conn, args.sql), indent=2, default=str))
            return 0
        files = args.files or [HERE / f for f in DEFAULT_FILES]
        failed = 0
        for f in files:
            failed += sum(not r["ok"] for r in run_file(conn, f))
        print(f"\nDone. {failed} statement(s) failed. Results in {RESULTS}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
