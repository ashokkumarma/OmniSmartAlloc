"""Bootstrap the workspace (stdlib only, idempotent). Run: py -3.12 scripts/setup.py  (or python3 scripts/setup.py)

1. Checks Python 3.11+, Git, Docker CLI.  2. Creates .venv and installs requirements.txt.
3. Copies .env.example -> .env if missing.  4. Checks the Docker daemon for local Zetaris.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
problems: list[str] = []


def log(status: str, msg: str) -> None:
    print(f"[{status}] {msg}")
    if status == "FAIL":
        problems.append(msg)


def tool_version(cmd: list[str]) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    res = subprocess.run(cmd, capture_output=True, text=True)
    return (res.stdout.strip() or res.stderr.strip()) if res.returncode == 0 else None


def main() -> int:
    if sys.version_info < (3, 11):
        log("FAIL", f"Python 3.11+ required, running {sys.version.split()[0]}")
        return 1
    log("PASS", f"Python {sys.version.split()[0]}")
    for name, cmd in (("Git", ["git", "--version"]), ("Docker CLI", ["docker", "--version"])):
        v = tool_version(cmd)
        log("PASS" if v else "FAIL", f"{name}: {v or 'not found on PATH'}")

    if not VENV_PY.exists():
        print("Creating .venv ...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    log("PASS", f".venv at {VENV}")
    print("Installing requirements.txt ...")
    pip = [str(VENV_PY), "-m", "pip", "install", "--disable-pip-version-check", "-q"]
    if subprocess.run(pip + ["--upgrade", "pip"]).returncode or subprocess.run(pip + ["-r", str(ROOT / "requirements.txt")]).returncode:
        log("FAIL", "dependency installation failed (see pip output above)")
    else:
        log("PASS", "dependencies installed")

    env_file, example = ROOT / ".env", ROOT / ".env.example"
    if env_file.exists():
        log("PASS", ".env already exists (left untouched)")
    else:
        shutil.copyfile(example, env_file)
        log("PASS", ".env created from .env.example - fill in your credentials")

    daemon = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True) \
        if shutil.which("docker") else None
    if daemon and daemon.returncode == 0:
        log("PASS", f"Docker daemon running (server {daemon.stdout.strip()})")
    else:
        log("WARN", "Docker daemon not reachable - start Docker Desktop if Zetaris runs locally")

    activate = r".venv\Scripts\activate" if os.name == "nt" else "source .venv/bin/activate"
    print(f"\nNext: {activate}  then  python scripts/validate_stack.py")
    if problems:
        print("\nSetup finished with problems:\n  - " + "\n  - ".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
