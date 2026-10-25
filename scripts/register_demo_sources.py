"""Register the OmniSmartAlloc demo sources in Zetaris. WRITES to the instance.

Default is a dry run (prints statements). Pass --execute only after user approval.

    python scripts/register_demo_sources.py            # dry run
    python scripts/register_demo_sources.py --execute  # run the CREATEs
    python scripts/register_demo_sources.py --file demo/register_channel_sources.sql --execute

${CHANNELS_DB_PASSWORD} in a SQL file is replaced from the environment (default: local demo password).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import MissingSetting, get_settings

SQL_FILE = Path(__file__).resolve().parent.parent / "demo" / "register_sources.sql"
DRIVER_CLASS = "com.zetaris.lightning.jdbc.LightningDriver"


def statements(sql_file: Path = SQL_FILE, secrets: bool = False) -> list[str]:
    text = sql_file.read_text()
    if secrets:
        text = text.replace("${CHANNELS_DB_PASSWORD}", os.environ.get("CHANNELS_DB_PASSWORD", "omni_demo_pw"))
    out = []
    for chunk in text.split(";"):
        lines = [ln for ln in chunk.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            out.append(stmt)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true", help="actually run the CREATE statements (writes to Zetaris)")
    ap.add_argument("--file", type=Path, default=SQL_FILE, help="SQL file to apply")
    args = ap.parse_args()

    stmts = statements(args.file)
    print(f"{len(stmts)} statements in {args.file.name}:\n")
    for i, s in enumerate(stmts, 1):
        print(f"-- [{i}] {s.splitlines()[0]} ...")

    if not args.execute:
        print("\nDry run only. Re-run with --execute to apply (writes to Zetaris).")
        return 0

    s = get_settings()
    try:
        s.require("zetaris_jdbc_url", "zetaris_jdbc_jar", "zetaris_username", "zetaris_password")
    except MissingSetting as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    import jaydebeapi

    conn = jaydebeapi.connect(DRIVER_CLASS, s.zetaris_jdbc_url,
                            [s.zetaris_username, s.zetaris_password], s.zetaris_jdbc_jar)
    try:
        cur = conn.cursor()
        for i, stmt in enumerate(statements(args.file, secrets=True), 1):
            try:
                cur.execute(stmt)
                print(f"[{i}] OK: {stmt.splitlines()[0]}")
            except Exception as e:
                msg = str(e)
                if "already" in msg.lower():
                    print(f"[{i}] SKIP (already exists): {stmt.splitlines()[0]}")
                else:
                    print(f"[{i}] FAIL: {stmt.splitlines()[0]}\n     {msg[:300]}", file=sys.stderr)
                    return 1
    finally:
        conn.close()
    print("\nRegistered. Verify: SHOW LIGHTNING DATABASES")
    return 0


if __name__ == "__main__":
    sys.exit(main())
