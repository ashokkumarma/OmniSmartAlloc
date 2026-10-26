"""Start the OmniSmartAlloc demo stack: channel order DB + source REST APIs + UI server.

Assumes the Zetaris platform is already up (cd zetaris-platform && docker compose up -d).
Each component is started in the background; Ctrl+C stops the UI but leaves the DB/APIs running.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
APP = ROOT / "demo" / "app"


def _wait(url: str, tries: int = 60) -> bool:
    for _ in range(tries):
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def _db_reachable() -> bool:
    sys.path.insert(0, str(ROOT / "demo"))
    import order_stores
    import psycopg
    try:
        psycopg.connect(order_stores.DB_URL, connect_timeout=3).close()
        return True
    except psycopg.OperationalError:
        return False


def _build_app() -> None:
    """Build the React UI (demo/app) on first run. Without Node the original pages are served instead."""
    if (APP / "dist" / "index.html").is_file():
        print("      UI already built")
        return
    npm = shutil.which("npm")
    if not npm:
        print("      Node.js not found: serving the original pages. Install Node 20+ and rerun for the new UI.")
        return
    try:
        if not (APP / "node_modules").is_dir():
            subprocess.run([npm, "ci", "--no-fund", "--no-audit"], cwd=APP, check=True)
        subprocess.run([npm, "run", "build"], cwd=APP, check=True)
    except subprocess.CalledProcessError:
        print("      UI build failed: serving the original pages. Run `npm run build` in demo/app to see why.", file=sys.stderr)


def main() -> int:
    print("[0/3] UI build...")
    _build_app()
    print("[1/3] channel order DB (Postgres)...")
    if _db_reachable():
        print("      already reachable on host port 5433, skipping docker compose")
    else:
        subprocess.run(["docker", "compose", "-f", "demo/docker-compose.channels.yml", "up", "-d", "--wait"],
                       cwd=ROOT, check=True)
        print("      omni-channels-db healthy (host port 5433)")

    print("[2/3] source REST APIs on :8901...")
    subprocess.Popen([PY, "demo/mock_apis.py", "8901"], cwd=ROOT,
                     stdout=open(ROOT / "demo" / "mock_apis.log", "w"), stderr=subprocess.STDOUT)
    if not _wait("http://localhost:8901/health"):
        print("      FAILED to start mock APIs — see demo/mock_apis.log", file=sys.stderr)
        return 1
    print("      mock APIs up:", json.dumps(["/api/wms/inventory", "/api/amazon/orders"]))

    print("[3/3] demo UI on :8902...")
    print()
    print("  App      : http://localhost:8902/")
    print("  (the original pages stay at /classic/channels and /classic/ops)")
    print()
    return subprocess.call([PY, "demo/server.py"], cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
