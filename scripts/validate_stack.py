"""Validate the Open Agent Hackathon 2026 stack: system, Zetaris, Nemotron/Meterless, Cursor config.

Usage: python scripts/validate_stack.py [--skip-network]
Exit code 0 when there are no FAIL results, 1 otherwise. Secrets are never printed.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"
PLACEHOLDER_RE = re.compile(r"^$|your[_-]|changeme|placeholder|<.*>|^x{3,}|^rt-local$|^nvapi-\.\.\.$", re.I)
REQUIRED_PACKAGES = {
    "openai": "openai",
    "pydantic": "pydantic",
    "dotenv": "python-dotenv",
    "requests": "requests",
    "rich": "rich",
    "docker": "docker",
    "jaydebeapi": "JayDeBeApi",
    "pytest": "pytest",
}
ZETARIS_DRIVER_CLASS = "com.zetaris.lightning.jdbc.LightningDriver"


@dataclass
class Report:
    results: list[tuple[str, str, str, str]] = field(default_factory=list)
    missing: dict[str, str] = field(default_factory=dict)

    def add(self, section: str, check: str, status: str, detail: str = "") -> str:
        self.results.append((section, check, status, detail))
        return status

    def need(self, var: str, how: str) -> None:
        self.missing.setdefault(var, how)


def env(name: str) -> str:
    return os.environ.get(name, "").strip()


def is_set(name: str) -> bool:
    return not PLACEHOLDER_RE.search(env(name))


def load_env_files(report: Report) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        report.add("Config", ".env loading", WARN, "python-dotenv not installed; using process env only")
        return
    found = [p for p in (ROOT / ".env.local", ROOT / ".env") if p.is_file()]
    for p in found:
        load_dotenv(p, override=False)
    if found:
        report.add("Config", ".env loading", PASS, ", ".join(p.name for p in found))
    else:
        report.add("Config", ".env loading", FAIL, "no .env or .env.local at repo root")
        report.need(".env", "Copy .env.example to .env")


def run(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ---------------------------------------------------------------- system
def check_python(report: Report) -> None:
    v = sys.version_info
    ver = f"{v.major}.{v.minor}.{v.micro}"
    report.add("System", "Python >= 3.10", PASS if v >= (3, 10) else FAIL, ver)
    in_venv = sys.prefix != sys.base_prefix
    expected = (ROOT / ".venv").resolve()
    if in_venv and Path(sys.prefix).resolve() == expected:
        report.add("System", "Running inside .venv", PASS, str(expected))
    elif in_venv:
        report.add("System", "Running inside .venv", WARN, f"in a different venv: {sys.prefix}")
    else:
        report.add("System", "Running inside .venv", FAIL, "not in a virtualenv; activate .venv first")

    missing = []
    for mod, pkg in REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(pkg)
    report.add("System", "Python dependencies", FAIL if missing else PASS,
               ("missing: " + ", ".join(missing)) if missing else f"{len(REQUIRED_PACKAGES)} packages importable")


def check_java(report: Report) -> bool:
    java_home = env("JAVA_HOME")
    if not java_home:
        report.add("System", "JAVA_HOME", FAIL, "not set")
        report.need("JAVA_HOME", "Set to your JDK 11+ folder (system env var or .env)")
        return False
    exe = Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")
    if not exe.is_file():
        hint = ""
        on_path = shutil.which("java")
        if on_path:
            hint = f"; a java exists on PATH ({on_path}) but JAVA_HOME must point at the JDK root"
        report.add("System", "JAVA_HOME/bin/java", FAIL, f"{exe} not found{hint}")
        report.need("JAVA_HOME", "Point to the JDK root folder (the one containing bin/java)")
        return False
    try:
        out = run([str(exe), "-version"]).stderr
    except Exception as e:
        report.add("System", "Java JDK >= 11", FAIL, f"could not run java: {e}")
        return False
    m = re.search(r'version "(\d+)(?:\.(\d+))?', out)
    if not m:
        report.add("System", "Java JDK >= 11", WARN, "could not parse java -version output")
        return True
    major = int(m.group(1)) if m.group(1) != "1" else int(m.group(2) or 0)
    report.add("System", "Java JDK >= 11", PASS if major >= 11 else FAIL, f"{out.splitlines()[0]} at {java_home}")
    return major >= 11


def check_docker(report: Report) -> None:
    required = env("ZETARIS_USE_DOCKER").lower() not in ("false", "0", "no")
    bad = FAIL if required else WARN
    if not shutil.which("docker"):
        report.add("System", "Docker CLI", bad, "docker not on PATH")
        return
    try:
        res = run(["docker", "info", "--format", "{{.ServerVersion}}"])
    except Exception as e:
        report.add("System", "Docker daemon", bad, str(e))
        return
    if res.returncode != 0:
        report.add("System", "Docker daemon", bad, "daemon not reachable; start Docker Desktop")
        return
    report.add("System", "Docker daemon", PASS, f"server {res.stdout.strip()}")
    if not required:
        return
    ps = run(["docker", "ps", "--format", "{{.Names}} {{.Image}} {{.Status}}"])
    zet = [line for line in ps.stdout.splitlines() if "zetaris" in line.lower()]
    report.add("Zetaris", "Zetaris containers running", PASS if zet else WARN,
               f"{len(zet)} running" if zet else "no running container with 'zetaris' in name/image")


# ---------------------------------------------------------------- zetaris
def parse_jdbc(url: str) -> tuple[str, int] | None:
    m = re.match(r"^jdbc:zetaris:lightning@([^:/]+):(\d+)", url)
    return (m.group(1), int(m.group(2))) if m else None


def tcp_ping(host: str, port: int, timeout: float = 3.0) -> str | None:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return None
    except OSError as e:
        return str(e)


def check_zetaris(report: Report, java_ok: bool, network: bool) -> None:
    guide = {
        "ZETARIS_JDBC_URL": "jdbc:zetaris:lightning@localhost:10000 locally, or the URL supplied to you",
        "ZETARIS_USERNAME": "Your Zetaris user ID",
        "ZETARIS_PASSWORD": "Your Zetaris password",
        "ZETARIS_REST_URL": "http://localhost:8888/api/v1.0 locally, or the supplied API base",
    }
    for var, how in guide.items():
        ok = is_set(var)
        report.add("Zetaris", var, PASS if ok else FAIL, "set" if ok else "missing/placeholder")
        if not ok:
            report.need(var, how)
    for var, how in {"ZETARIS_API_KEY": "Zetaris UI -> Management -> API Tokens -> +",
                     "ZETARIS_ORG_ID": "Zetaris UI -> Management -> Organisation -> ID (numeric)"}.items():
        ok = is_set(var)
        report.add("Zetaris", f"{var} (direct REST)", PASS if ok else WARN, "set" if ok else "not set (optional for JDBC)")
        if not ok:
            report.need(var, how + "  [optional]")

    jar = env("ZETARIS_JDBC_JAR")
    jar_ok = bool(jar) and Path(jar).is_file() and jar.lower().endswith(".jar")
    if not jar:
        report.add("Zetaris", "ZETARIS_JDBC_JAR", FAIL, "not set")
    else:
        report.add("Zetaris", "ZETARIS_JDBC_JAR", PASS if jar_ok else FAIL,
                   Path(jar).name if jar_ok else f"file not found or not a .jar: {jar}")
    if not jar_ok:
        report.need("ZETARIS_JDBC_JAR", "Full path to <repo>/zetaris-platform/jdbc/ndp-jdbc-driver-*.jar")

    if not network:
        report.add("Zetaris", "Connectivity", SKIP, "--skip-network")
        return

    hp = parse_jdbc(env("ZETARIS_JDBC_URL")) if is_set("ZETARIS_JDBC_URL") else None
    port_ok = False
    if hp:
        err = tcp_ping(*hp)
        port_ok = err is None
        report.add("Zetaris", f"JDBC port {hp[0]}:{hp[1]}", PASS if port_ok else FAIL, "reachable" if port_ok else err)
    elif is_set("ZETARIS_JDBC_URL"):
        report.add("Zetaris", "JDBC URL format", FAIL, "expected jdbc:zetaris:lightning@host:port")

    creds = is_set("ZETARIS_USERNAME") and is_set("ZETARIS_PASSWORD")
    if is_set("ZETARIS_REST_URL") and creds:
        check_zetaris_rest(report)
    else:
        report.add("Zetaris", "REST ping", SKIP, "needs ZETARIS_REST_URL, USERNAME, PASSWORD")

    if java_ok and jar_ok and port_ok and creds:
        check_zetaris_jdbc(report, jar)
    else:
        report.add("Zetaris", "JDBC SELECT 1", SKIP, "needs Java 11+, JAR, reachable port and credentials")


def check_zetaris_rest(report: Report) -> None:
    import requests

    base = env("ZETARIS_REST_URL").rstrip("/")
    root = base[: -len("/api/v1.0")] if base.endswith("/api/v1.0") else base
    url = f"{root}/redoc/docs.yaml"
    try:
        r = requests.get(url, auth=(env("ZETARIS_USERNAME"), env("ZETARIS_PASSWORD")), timeout=10)
    except requests.RequestException as e:
        report.add("Zetaris", "REST ping (OpenAPI spec)", FAIL, f"{urlparse(url).netloc}: {type(e).__name__}")
        return
    if r.status_code == 200:
        report.add("Zetaris", "REST ping (OpenAPI spec)", PASS, f"HTTP 200 from {urlparse(url).netloc}")
    elif r.status_code in (401, 403):
        report.add("Zetaris", "REST ping (OpenAPI spec)", FAIL, f"HTTP {r.status_code}: check username/password")
    else:
        report.add("Zetaris", "REST ping (OpenAPI spec)", WARN, f"HTTP {r.status_code}")


def check_zetaris_jdbc(report: Report, jar: str) -> None:
    try:
        import jaydebeapi

        conn = jaydebeapi.connect(ZETARIS_DRIVER_CLASS, env("ZETARIS_JDBC_URL"),
                                  [env("ZETARIS_USERNAME"), env("ZETARIS_PASSWORD")], jar)
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            row = cur.fetchone()
        finally:
            conn.close()
        ok = row is not None and str(row[0]).split(".")[0] == "1"
        report.add("Zetaris", "JDBC SELECT 1", PASS if ok else FAIL, f"returned {row}")
    except Exception as e:
        report.add("Zetaris", "JDBC SELECT 1", FAIL, f"{type(e).__name__}: {str(e)[:160]}")


# ---------------------------------------------------------------- inference
def check_inference(report: Report, network: bool) -> None:
    nim, met = is_set("NVIDIA_NIM_API_KEY"), is_set("METERLESS_API_KEY")
    if not (nim or met):
        report.add("Inference", "NVIDIA_NIM_API_KEY or METERLESS_API_KEY", FAIL, "neither is set")
        report.need("NVIDIA_NIM_API_KEY", "https://build.nvidia.com -> any Nemotron model -> Get API Key (nvapi-...)")
        report.need("METERLESS_API_KEY", "Meterless Runtime token from <stateDir>/proxy-token  [alternative to NIM]")
        return
    report.add("Inference", "API key present", PASS, ", ".join(n for n, s in (("NIM", nim), ("Meterless", met)) if s))
    if not network:
        report.add("Inference", "Endpoint ping", SKIP, "--skip-network")
        return
    if nim:
        ping_openai(report, "NVIDIA NIM", env("NVIDIA_NIM_BASE_URL") or "https://integrate.api.nvidia.com/v1",
                    env("NVIDIA_NIM_API_KEY"), {}, model_filter="nemotron")
    if met:
        app = env("METERLESS_APP_ID") or "open-agent-hackathon"
        ping_openai(report, "Meterless", env("METERLESS_BASE_URL") or "http://127.0.0.1:8088/v1",
                    env("METERLESS_API_KEY"), {"meterless-app": app}, model_filter="meterless/")


def ping_openai(report: Report, label: str, base_url: str, key: str, headers: dict, model_filter: str) -> None:
    try:
        import openai
    except ImportError:
        report.add("Inference", f"{label} ping", SKIP, "openai package not installed")
        return
    client = openai.OpenAI(base_url=base_url, api_key=key, default_headers=headers, timeout=30, max_retries=0)
    host = urlparse(base_url).netloc
    try:
        ids = [m.id for m in client.models.list()]
    except openai.AuthenticationError:
        report.add("Inference", f"{label} models.list", FAIL, f"401 unauthorized at {host}: key invalid")
        return
    except openai.PermissionDeniedError:
        report.add("Inference", f"{label} models.list", FAIL, f"403 forbidden at {host}")
        return
    except openai.APIConnectionError:
        report.add("Inference", f"{label} models.list", FAIL, f"cannot reach {host} (offline?)")
        return
    except openai.APIError as e:
        report.add("Inference", f"{label} models.list", FAIL, f"{type(e).__name__} at {host}")
        return
    matched = [i for i in ids if model_filter in i.lower()]
    report.add("Inference", f"{label} models.list", PASS if matched else WARN,
               f"{len(ids)} models, {len(matched)} match '{model_filter}'")

    model = env("NEMOTRON_MODEL") if label == "NVIDIA NIM" else ("meterless/auto" if "meterless/auto" in ids else None)
    if not model:
        report.add("Inference", f"{label} completion", SKIP,
                   "set NEMOTRON_MODEL to an id from models.list to test a completion" if label == "NVIDIA NIM"
                   else "meterless/auto not advertised")
        return
    try:
        extra = {"extra_headers": {"meterless-scope": "user"}} if label == "Meterless" else {}
        resp = client.chat.completions.create(model=model, max_tokens=16, temperature=0,
                                              messages=[{"role": "user", "content": "Reply with: ok"}], **extra)
        report.add("Inference", f"{label} completion", PASS, f"{model} responded ({resp.usage.total_tokens if resp.usage else '?'} tokens)")
    except openai.NotFoundError:
        report.add("Inference", f"{label} completion", FAIL, f"model '{model}' not found")
    except openai.APIError as e:
        report.add("Inference", f"{label} completion", FAIL, f"{type(e).__name__}: {str(e)[:120]}")


# ---------------------------------------------------------------- editor
def check_editor(report: Report) -> None:
    root_rules = ROOT / ".cursorrules"
    mdc = list((ROOT / ".cursor" / "rules").glob("*.mdc")) if (ROOT / ".cursor" / "rules").is_dir() else []
    found = ([".cursorrules"] if root_rules.is_file() else []) + [f".cursor/rules/{p.name}" for p in mdc]
    report.add("Editor", "Cursor rules", PASS if found else FAIL, ", ".join(found) or "no .cursorrules or .cursor/rules/*.mdc")


# ---------------------------------------------------------------- tests
def check_smoke_tests(report: Report) -> None:
    if importlib.util.find_spec("pytest") is None:
        report.add("Tests", "pytest ReAct smoke test", SKIP, "pytest not installed")
        return
    try:
        res = subprocess.run([sys.executable, "-m", "pytest", "--no-header", "-p", "no:cacheprovider"],
                             cwd=ROOT, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        report.add("Tests", "pytest ReAct smoke test", FAIL, "timed out after 300 s")
        return
    lines = [ln for ln in res.stdout.strip().splitlines() if ln.strip()]
    report.add("Tests", "pytest (3-step ReAct smoke + guards)", PASS if res.returncode == 0 else FAIL,
               lines[-1] if lines else f"exit code {res.returncode}")


# ---------------------------------------------------------------- output
def render(report: Report) -> None:
    colors = {PASS: "green", FAIL: "red", WARN: "yellow", SKIP: "cyan"}
    counts = {s: sum(1 for r in report.results if r[2] == s) for s in colors}
    try:
        from rich.console import Console
        from rich.markup import escape
        from rich.table import Table
    except ImportError:
        for sec, chk, st, det in report.results:
            print(f"[{st}] {sec:<9} {chk:<38} {det}")
        print("Summary: " + "  ".join(f"{k}={v}" for k, v in counts.items()))
        if report.missing:
            print("\nMissing inputs (fill these in .env):")
            for var, how in report.missing.items():
                print(f"  {var:<22} {how}")
        return
    console = Console()
    t = Table(title="Open Agent Hackathon 2026 - Stack Validation", show_lines=False)
    for col in ("Section", "Check", "Status", "Detail"):
        t.add_column(col, overflow="fold")
    for sec, chk, st, det in report.results:
        t.add_row(escape(sec), escape(chk), f"[bold {colors[st]}]\\[{st}][/]", escape(det))
    console.print(t)
    console.print("Summary: " + "  ".join(f"[{colors[k]}]{k}={v}[/]" for k, v in counts.items()))
    if report.missing:
        m = Table(title="Missing inputs - fill these in .env (never paste secrets into chat)", title_style="bold yellow")
        m.add_column("Variable", style="bold")
        m.add_column("Where to get it / what to set")
        for var, how in report.missing.items():
            m.add_row(escape(var), escape(how))
        console.print(m)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-network", action="store_true", help="skip all network/connectivity checks")
    args = ap.parse_args()
    report = Report()
    load_env_files(report)
    check_python(report)
    java_ok = check_java(report)
    check_docker(report)
    check_zetaris(report, java_ok, not args.skip_network)
    check_inference(report, not args.skip_network)
    check_editor(report)
    check_smoke_tests(report)
    render(report)
    return 1 if any(r[2] == FAIL for r in report.results) else 0


if __name__ == "__main__":
    sys.exit(main())
