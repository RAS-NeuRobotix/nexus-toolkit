"""Discover, update, and run Nexus automated tests (nexus-tests repo)."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.request import urlopen

from nexus_toolkit.paths import LOGS_DIR, NEXUS_TESTS_DIR, NEXUS_TESTS_GIT

DEFAULT_NEXUS_TESTS_DIR = NEXUS_TESTS_DIR
DEFAULT_NEXUS_TESTS_GIT = NEXUS_TESTS_GIT
DEFAULT_VITE_URL = "http://localhost:5173"
TOOLKIT_TEST_RUNS_DIR = LOGS_DIR / "test-runs"
TOOLKIT_ALLURE_ROOT = LOGS_DIR / "allure"
ALLURE_HISTORY_MAX_BUILDS = 20
ALLURE_ARCHIVE_MAX_RUNS = 20
_ALLURE_TREND_JSON_FILES = (
    "history-trend.json",
    "duration-trend.json",
    "retries-trend.json",
    "categories-trend.json",
)

OnLine = Callable[[str], None]


def _writable_run_dir(stamp: str | None = None) -> Path:
    """Reports under ~/nexus-toolkit-logs — nexus-tests/reports may be root-owned."""
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = TOOLKIT_TEST_RUNS_DIR / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _pytest_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    # nexus-tests conftest rewrites html/junit to reports/ unless GITHUB_ACTIONS=true.
    # Keep our absolute toolkit paths so writes succeed when reports/ is not writable.
    env = {**os.environ, "GITHUB_ACTIONS": "true"}
    if extra:
        env.update(extra)
    return env


@dataclass
class TestRunOptions:
    headless: bool = True
    parallel: bool = False
    parallel_workers: int = 2
    allure: bool = False
    drone: bool = True
    lab: bool = False
    flight: bool = False
    reruns: int = 1
    browser: str = "chromium"
    marker_expression: str = ""
    suite_path: str = "tests/"


@dataclass
class TestCaseResult:
    nodeid: str
    outcome: str  # passed | failed | skipped | error
    message: str = ""


@dataclass
class TestRunSummary:
    selected_count: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    exit_code: int = 0
    html_report: Optional[Path] = None
    junit_report: Optional[Path] = None
    allure_report_dir: Optional[Path] = None
    allure_archive_dir: Optional[Path] = None
    allure_error: str = ""
    cases: list[TestCaseResult] = field(default_factory=list)
    command: str = ""

    @property
    def total_executed(self) -> int:
        return self.passed + self.failed + self.skipped + self.errors


@dataclass(frozen=True)
class AllureDirs:
    root: Path
    results: Path
    report: Path
    runs: Path


def allure_dirs() -> AllureDirs:
    root = TOOLKIT_ALLURE_ROOT
    return AllureDirs(
        root=root,
        results=root / "allure-results",
        report=root / "allure-report",
        runs=root / "runs",
    )


def _resolve_allure_bin(repo_dir: Path | None = None) -> str | None:
    env_bin = os.environ.get("ALLURE_BIN", "").strip()
    if env_bin and Path(env_bin).is_file():
        return env_bin
    which = shutil.which("allure")
    if which:
        return which
    if repo_dir is not None:
        local = repo_dir / ".tools" / "bin" / "allure"
        if local.is_file():
            return str(local)
    return None


def _allure_generate_argv(results_dir: Path, out_dir: Path, repo_dir: Path | None = None) -> list[str] | None:
    allure_bin = _resolve_allure_bin(repo_dir)
    r_abs = str(results_dir.resolve())
    o_abs = str(out_dir.resolve())
    if allure_bin:
        return [allure_bin, "generate", r_abs, "-o", o_abs, "--clean"]
    if shutil.which("npx"):
        return ["npx", "--yes", "allure-commandline", "generate", r_abs, "-o", o_abs, "--clean"]
    return None


def _recompute_allure_statistic(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"failed": 0, "broken": 0, "skipped": 0, "passed": 0, "unknown": 0}
    for it in items:
        st = str(it.get("status", "unknown")).lower()
        if st in counts:
            counts[st] += 1
        else:
            counts["unknown"] += 1
    counts["total"] = len(items)
    return counts


def _trim_allure_test_items(items: list[dict[str, Any]], max_runs: int) -> list[dict[str, Any]]:
    if len(items) <= max_runs:
        return items

    def sort_key(it: dict[str, Any]) -> int:
        t = it.get("time") or {}
        return int(t.get("stop") or t.get("start") or 0)

    return sorted(items, key=sort_key)[-max_runs:]


def _trim_allure_history_json(path: Path, max_builds: int) -> None:
    with path.open(encoding="utf-8") as f:
        root = json.load(f)
    if not isinstance(root, dict):
        return
    changed = False
    for _hid, entry in root.items():
        if not isinstance(entry, dict):
            continue
        items = entry.get("items")
        if not isinstance(items, list):
            continue
        trimmed = _trim_allure_test_items(items, max_builds)
        if len(trimmed) != len(items):
            entry["items"] = trimmed
            entry["statistic"] = _recompute_allure_statistic(trimmed)
            changed = True
    if changed:
        with path.open("w", encoding="utf-8") as f:
            json.dump(root, f, ensure_ascii=False)


def _trim_allure_trend_json(path: Path, max_builds: int) -> None:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or len(data) <= max_builds:
        return
    ordered = sorted(data, key=lambda x: int(x.get("buildOrder") or 0))
    trimmed = ordered[-max_builds:]
    with path.open("w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False)


def trim_allure_history_dir(history_dir: Path, max_builds: int = ALLURE_HISTORY_MAX_BUILDS) -> None:
    """Keep only the last *max_builds* entries (Allure Report 2 ``history/`` layout)."""
    hist_json = history_dir / "history.json"
    if hist_json.is_file():
        _trim_allure_history_json(hist_json, max_builds)
    for name in _ALLURE_TREND_JSON_FILES:
        p = history_dir / name
        if p.is_file():
            _trim_allure_trend_json(p, max_builds)


def prepare_allure(
    history_max: int = ALLURE_HISTORY_MAX_BUILDS,
    on_line: Optional[OnLine] = None,
) -> Path:
    """Wipe toolkit allure-results; restore + trim history from the last report."""
    log = on_line or (lambda _msg: None)
    dirs = allure_dirs()
    report_hist = dirs.report / "history"
    results_hist = dirs.results / "history"
    if report_hist.is_dir():
        history_src: Path | None = report_hist
    elif results_hist.is_dir():
        history_src = results_hist
    else:
        history_src = None

    if dirs.results.is_dir():
        shutil.rmtree(dirs.results)
    dirs.results.mkdir(parents=True, exist_ok=True)

    if history_src is not None:
        dest_hist = dirs.results / "history"
        shutil.copytree(history_src, dest_hist)
        log(f"Allure: restored history from {history_src}")
        if history_max > 0:
            trim_allure_history_dir(dest_hist, history_max)
            log(f"Allure: trimmed history to last {history_max} build(s)")
    else:
        log(f"Allure: no prior history — Trends will start fresh at {dirs.results}")
    return dirs.results


def generate_allure_report(
    repo_dir: Path | None = None,
    on_line: Optional[OnLine] = None,
) -> tuple[bool, Path | None, str]:
    """Run ``allure generate`` into the toolkit allure-report directory."""
    log = on_line or (lambda _msg: None)
    dirs = allure_dirs()
    if not dirs.results.is_dir():
        return False, None, f"Allure results missing: {dirs.results}"
    argv = _allure_generate_argv(dirs.results, dirs.report, repo_dir=repo_dir)
    if not argv:
        msg = (
            "Allure CLI not found. Install Allure commandline, set ALLURE_BIN, "
            "or ensure npx is available."
        )
        log(msg)
        return False, None, msg
    log(f"Allure: generating report → {dirs.report}")
    result = subprocess.run(argv, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
        log(f"Allure generate failed: {err}")
        return False, None, err
    if not (dirs.report / "index.html").is_file():
        msg = f"Allure generate produced no index.html under {dirs.report}"
        log(msg)
        return False, None, msg
    log(f"Allure report: {dirs.report}")
    return True, dirs.report, ""


def archive_allure_report(
    max_runs: int = ALLURE_ARCHIVE_MAX_RUNS,
    stamp: str | None = None,
    on_line: Optional[OnLine] = None,
) -> Path | None:
    """Copy the latest allure-report into runs/<stamp>/ and prune older archives."""
    log = on_line or (lambda _msg: None)
    dirs = allure_dirs()
    if not (dirs.report / "index.html").is_file():
        return None
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    dirs.runs.mkdir(parents=True, exist_ok=True)
    dest = dirs.runs / stamp
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(dirs.report, dest)
    log(f"Allure: archived as run {stamp}")

    archives = sorted(
        [p for p in dirs.runs.iterdir() if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    for old in archives[max(0, max_runs) :]:
        try:
            shutil.rmtree(old)
            log(f"Allure: pruned old archive {old.name}")
        except OSError as exc:
            log(f"Allure: could not prune {old.name}: {exc}")
    return dest


def list_allure_archives() -> list[Path]:
    """Newest-first list of archived Allure report directories (≤20 kept on disk)."""
    runs = allure_dirs().runs
    if not runs.is_dir():
        return []
    return sorted(
        [p for p in runs.iterdir() if p.is_dir() and (p / "index.html").is_file()],
        key=lambda p: p.name,
        reverse=True,
    )


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def open_allure_report(report_dir: Path | None = None) -> tuple[bool, str]:
    """Serve an Allure HTML report over loopback HTTP and open the browser."""
    dirs = allure_dirs()
    root = (report_dir or dirs.report).resolve()
    index = root / "index.html"
    if not index.is_file():
        return False, f"Allure index not found: {index}"
    port = _pick_free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(port),
            "--bind",
            "127.0.0.1",
            "--directory",
            str(root),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    url = f"http://127.0.0.1:{port}/"
    time.sleep(0.4)
    if proc.poll() is not None:
        return False, f"HTTP server exited; try: python -m http.server --directory {root}"
    webbrowser.open(url)
    return True, f"Opened {url} (server PID {proc.pid})"


SUITE_PRESETS: dict[str, tuple[str, str]] = {
    # label -> (suite_path, marker_expression)
    "All tests": ("tests/", ""),
    "API only": ("tests/api", ""),
    "E2E only": ("tests/e2e", ""),
    "Performance": ("tests/", "performance"),
    "Smoke": ("tests/", "smoke"),
    "Sanity": ("tests/", "sanity"),
    "Lab": ("tests/", "lab"),
    "Flight": ("tests/", "flight"),
}


@dataclass(frozen=True)
class CollectedTest:
    """One collected pytest item with its docstring description."""

    nodeid: str
    description: str = ""


@dataclass(frozen=True)
class TestDisplayInfo:
    """Human-readable parts derived from a pytest nodeid (+ optional docstring)."""

    nodeid: str
    kind: str  # API, E2E, Performance, …
    group: str  # e.g. "API · nfz"
    title: str  # docstring description (preferred) or humanized name
    module: str  # file stem without test_ prefix
    description: str = ""


def parse_test_display(nodeid: str, description: str = "") -> TestDisplayInfo:
    """Build UI labels; prefer the test docstring as the visible title."""
    path_part, _, func_part = nodeid.partition("::")
    path_part = path_part.replace("\\", "/")
    parts = [p for p in path_part.split("/") if p]
    if parts and parts[0] == "tests":
        parts = parts[1:]

    kind_raw = parts[0] if parts else "other"
    kind = {
        "api": "API",
        "e2e": "E2E",
        "performance": "Performance",
        "unit": "Unit",
        "integration": "Integration",
    }.get(kind_raw.lower(), kind_raw.upper() if kind_raw else "Other")

    file_name = parts[-1] if parts else ""
    module_stem = Path(file_name).stem if file_name else ""
    if module_stem.startswith("test_"):
        module_stem = module_stem[5:]

    package_parts = parts[1:-1] if len(parts) > 1 else []
    package = " / ".join(package_parts) if package_parts else (module_stem or "misc")
    group = f"{kind} · {package}"

    clean_doc = _normalize_description(description)
    title = clean_doc or _humanize_test_function(func_part or module_stem or nodeid)
    # Keep parametrize id visible when docstring is shared across params
    _, bracket, params = (func_part or "").partition("[")
    if clean_doc and bracket and params:
        param = params.rstrip("]").strip()
        if param and f"[{param}]" not in clean_doc:
            title = f"{clean_doc}  [{param}]"

    return TestDisplayInfo(
        nodeid=nodeid,
        kind=kind,
        group=group,
        title=title,
        module=module_stem,
        description=clean_doc,
    )


def _normalize_description(text: str) -> str:
    if not text:
        return ""
    # First non-empty line of the docstring is the display title
    for line in text.strip().splitlines():
        cleaned = " ".join(line.split()).strip()
        if cleaned:
            # Drop markdown/pytest double-backticks so UI reads cleanly
            return cleaned.replace("``", "").replace("`", "")
    return ""


def _humanize_test_function(func_part: str) -> str:
    name, bracket, params = func_part.partition("[")
    name = name.strip()
    if name.startswith("test_"):
        name = name[5:]
    for suffix in ("_contract_api", "_contract", "_api", "_e2e", "_ui"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    title = name.replace("_", " ").strip() or func_part
    if bracket and params:
        param = params.rstrip("]").strip()
        if param:
            title = f"{title}  [{param}]"
    return title


_COLLECT_PLUGIN = '''\
"""Temp pytest plugin: write nodeid + docstring JSON for Nexus Toolkit."""
from __future__ import annotations

import inspect
import json
import os
from pathlib import Path


def _item_doc(item) -> str:
    """Prefer the live function docstring (item.obj / item.function)."""
    for candidate in (getattr(item, "obj", None), getattr(item, "function", None)):
        if candidate is None:
            continue
        doc = inspect.getdoc(candidate) or getattr(candidate, "__doc__", None)
        if doc:
            return doc
    return ""


def pytest_collection_finish(session):
    out = os.environ.get("NEXUS_TOOLKIT_COLLECT_JSON", "").strip()
    if not out:
        return
    rows = [{"nodeid": item.nodeid, "description": _item_doc(item)} for item in session.items]
    Path(out).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
'''


_RUN_PLUGIN = '''\
"""Temp pytest plugin: print docstring titles in the live log."""
from __future__ import annotations

import inspect

import pytest


def _item_title(item) -> str:
    doc = ""
    for candidate in (getattr(item, "obj", None), getattr(item, "function", None)):
        if candidate is None:
            continue
        doc = inspect.getdoc(candidate) or getattr(candidate, "__doc__", None) or ""
        if doc:
            break
    for line in (doc or "").strip().splitlines():
        cleaned = " ".join(line.split()).strip().replace("``", "").replace("`", "")
        if cleaned:
            nodeid = getattr(item, "nodeid", "") or ""
            _, bracket, params = nodeid.partition("[")
            if bracket and params:
                param = params.rstrip("]").strip()
                if param and f"[{param}]" not in cleaned:
                    cleaned = f"{cleaned}  [{param}]"
            return cleaned
    return getattr(item, "nodeid", "") or "?"


def pytest_runtest_setup(item):
    print(f"\\n>>> {_item_title(item)}", flush=True)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" and not (report.when == "setup" and report.skipped):
        return
    status = (report.outcome or "?").upper()
    print(f"[{status}] {_item_title(item)}", flush=True)
'''


def resolve_tests_python(repo_dir: Path) -> list[str]:
    venv_python = repo_dir / ".venv" / "bin" / "python"
    if venv_python.is_file():
        return [str(venv_python)]
    return ["python3"]


def check_vite_running(url: str = DEFAULT_VITE_URL, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310 — local preflight
            code = getattr(response, "status", 200)
            if 200 <= int(code) < 500:
                return True, f"Front is reachable at {url}"
            return False, f"Front returned HTTP {code} at {url}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Front is not running at {url} ({exc})"


def ensure_repo_dir(repo_dir: Path) -> tuple[bool, str]:
    if repo_dir.is_dir() and (repo_dir / "pyproject.toml").is_file():
        return True, f"Found nexus-tests at {repo_dir}"
    if repo_dir.exists() and not repo_dir.is_dir():
        return False, f"Path exists but is not a directory: {repo_dir}"
    return False, f"nexus-tests not found at {repo_dir} — use Clone / Update from Git"


def git_clone_or_pull(
    repo_dir: Path,
    git_url: str,
    on_line: Optional[OnLine] = None,
) -> tuple[bool, str]:
    log = on_line or (lambda _msg: None)
    repo_dir = repo_dir.expanduser()

    if repo_dir.is_dir() and (repo_dir / ".git").is_dir():
        log(f"=== git pull in {repo_dir} ===")
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "pull", "--ff-only"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = (result.stdout or result.stderr or "").strip()
        for line in out.splitlines():
            log(line)
        if result.returncode != 0:
            return False, out or "git pull failed"
        return True, "Repository updated (git pull)"

    if repo_dir.exists() and any(repo_dir.iterdir()):
        return False, f"Directory exists and is not a git repo: {repo_dir}"

    parent = repo_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    log(f"=== git clone {git_url} → {repo_dir} ===")
    result = subprocess.run(
        ["git", "clone", git_url, str(repo_dir)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    out = (result.stdout or result.stderr or "").strip()
    for line in out.splitlines():
        log(line)
    if result.returncode != 0:
        return False, out or "git clone failed"
    return True, f"Cloned to {repo_dir}"


def collect_tests(
    repo_dir: Path,
    *,
    suite_path: str = "tests/",
    marker_expression: str = "",
    drone: bool = True,
    lab: bool = False,
    on_line: Optional[OnLine] = None,
) -> tuple[bool, list[CollectedTest], str]:
    """Collect pytest items with docstring descriptions (no test execution)."""
    log = on_line or (lambda _msg: None)
    ok, message = ensure_repo_dir(repo_dir)
    if not ok:
        return False, [], message

    run_dir = _writable_run_dir()
    collect_log = run_dir / "collect.log"
    collect_json = run_dir / "collect.json"
    plugin_path = run_dir / "_nexus_toolkit_collect_plugin.py"
    plugin_path.write_text(_COLLECT_PLUGIN, encoding="utf-8")

    python = resolve_tests_python(repo_dir)
    cmd = [
        *python,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-p",
        "_nexus_toolkit_collect_plugin",
        "--override-ini",
        "addopts=",
        "--override-ini",
        f"log_file={collect_log}",
        f"--drone={'True' if drone else 'False'}",
        f"--lab={'true' if lab else 'false'}",
    ]
    if marker_expression.strip():
        cmd.extend(["-m", marker_expression.strip()])
    target = suite_path.strip() or "tests/"
    cmd.append(target)

    env = _pytest_env(
        {
            "HEADLESS": "true",
            "NEXUS_TOOLKIT_COLLECT_JSON": str(collect_json),
            "PYTHONPATH": f"{run_dir}{os.pathsep}{os.environ.get('PYTHONPATH', '')}",
        }
    )

    log("Collecting tests…")
    result = subprocess.run(
        cmd,
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    for line in combined.splitlines():
        if _should_log_collect_line(line):
            log(line)

    collected = _load_collected_tests(collect_json)
    if not collected:
        # Fallback: nodeids from stdout without descriptions (plugin missing / failed)
        log(
            "WARNING: collect plugin did not write descriptions "
            f"({collect_json}); falling back to nodeids only"
        )
        collected = [
            CollectedTest(nodeid=nodeid) for nodeid in _parse_collect_nodeids(result.stdout or "")
        ]
    elif not any(item.description for item in collected):
        log(
            "WARNING: collect returned empty descriptions for all tests — "
            "UI will show humanized function names"
        )

    if result.returncode not in (0, 5) and not collected:
        # 5 = no tests collected
        return False, [], (result.stderr or result.stdout or "collect failed").strip()
    return True, collected, f"Collected {len(collected)} tests"


def _load_collected_tests(path: Path) -> list[CollectedTest]:
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    out: list[CollectedTest] = []
    seen: set[str] = set()
    for row in raw:
        if not isinstance(row, dict):
            continue
        nodeid = str(row.get("nodeid") or "").strip()
        if not nodeid or nodeid in seen:
            continue
        seen.add(nodeid)
        out.append(
            CollectedTest(
                nodeid=nodeid,
                description=str(row.get("description") or ""),
            )
        )
    return out


def _should_log_collect_line(line: str) -> bool:
    """Hide raw nodeids / discovery noise from Live Log during collect."""
    s = line.strip()
    if not s:
        return False
    lower = s.lower()
    if "::" in s and (s.startswith("tests/") or s.startswith("tests\\")):
        return False
    if "drone ws discovery" in lower or "drone auto-discovery" in lower:
        return False
    if "using configured drone_id" in lower:
        return False
    if s.startswith("INTERNALERROR") or "error" in lower or "traceback" in lower:
        return True
    if "collected" in lower or "deselected" in lower:
        return True
    if s.startswith("="):
        return False
    return False


_NODEID_RE = re.compile(r"^[\w./\\-]+::[\w\[\]-]+(?:::[\w\[\]-]+)?$")


def _parse_collect_nodeids(stdout: str) -> list[str]:
    nodeids: list[str] = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line or line.startswith("=") or "test session" in line.lower():
            continue
        if " selected" in line or "deselected" in line or "collected" in line.lower():
            continue
        if line.startswith("<") or line.startswith("INTERNALERROR"):
            continue
        # Quiet collect lines are nodeids; sometimes prefixed with status chars
        candidate = line.split()[-1] if " " in line and "::" in line else line
        if "::" in candidate and candidate.startswith("tests"):
            nodeids.append(candidate)
        elif _NODEID_RE.match(candidate):
            nodeids.append(candidate)
    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for nodeid in nodeids:
        if nodeid not in seen:
            seen.add(nodeid)
            unique.append(nodeid)
    return unique


def run_tests(
    repo_dir: Path,
    selected_nodeids: list[str],
    options: TestRunOptions,
    on_line: Optional[OnLine] = None,
) -> tuple[bool, TestRunSummary]:
    log = on_line or (lambda _msg: None)
    summary = TestRunSummary(selected_count=len(selected_nodeids))

    ok, message = ensure_repo_dir(repo_dir)
    if not ok:
        summary.exit_code = 1
        return False, summary

    if not selected_nodeids:
        log("No tests selected")
        summary.exit_code = 1
        return False, summary

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = _writable_run_dir(stamp)
    html_report = run_dir / "report.html"
    junit_report = run_dir / "results.xml"
    run_log = run_dir / "pytest.log"
    plugin_path = run_dir / "_nexus_toolkit_run_plugin.py"
    plugin_path.write_text(_RUN_PLUGIN, encoding="utf-8")
    summary.html_report = html_report
    summary.junit_report = junit_report
    log(f"Reports directory: {run_dir}")

    python = resolve_tests_python(repo_dir)
    cmd = [
        *python,
        "-m",
        "pytest",
        "-v",
        "--tb=short",
        "-p",
        "_nexus_toolkit_run_plugin",
        "--override-ini",
        "addopts=",
        "--override-ini",
        f"log_file={run_log}",
        f"--browser={options.browser}",
        f"--drone={'True' if options.drone else 'False'}",
        f"--lab={'true' if options.lab else 'false'}",
        f"--reruns={max(0, options.reruns)}",
        f"--html={html_report}",
        "--self-contained-html",
        f"--junitxml={junit_report}",
    ]

    if options.parallel:
        cmd.extend(["-n", str(max(1, options.parallel_workers))])
    else:
        cmd.extend(["-n", "0"])

    # Selected nodeids already define the set — do not also apply -m filters.
    if options.allure:
        allure_results = prepare_allure(on_line=log)
        cmd.extend(["--alluredir", str(allure_results)])

    cmd.extend(selected_nodeids)

    env = _pytest_env(
        {
            "HEADLESS": "true" if options.headless else "false",
            "PYTHONPATH": f"{run_dir}{os.pathsep}{os.environ.get('PYTHONPATH', '')}",
        }
    )

    summary.command = " ".join(cmd)
    log(f"Running {len(selected_nodeids)} selected tests…")
    log(f"HEADLESS={env['HEADLESS']}")

    process = subprocess.Popen(
        cmd,
        cwd=str(repo_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    assert process.stdout is not None
    for line in process.stdout:
        text = line.rstrip("\n")
        if _should_log_run_line(text):
            log(text)
    exit_code = process.wait()
    summary.exit_code = exit_code

    if junit_report.is_file():
        _fill_summary_from_junit(summary, junit_report)
    else:
        log("JUnit report missing — summary counts may be incomplete")

    if options.allure:
        ok_gen, report_dir, err = generate_allure_report(repo_dir=repo_dir, on_line=log)
        if ok_gen and report_dir is not None:
            summary.allure_report_dir = report_dir
            archive_stamp = stamp.replace("_", "-")
            summary.allure_archive_dir = archive_allure_report(
                stamp=archive_stamp,
                on_line=log,
            )
        else:
            summary.allure_error = err or "Allure generate failed"
            log(f"Allure results kept at: {allure_dirs().results}")

    log("")
    log("=== Summary ===")
    log(f"Selected: {summary.selected_count}")
    log(f"Passed:   {summary.passed}")
    log(f"Failed:   {summary.failed}")
    log(f"Skipped:  {summary.skipped}")
    log(f"Errors:   {summary.errors}")
    if summary.html_report and summary.html_report.is_file():
        log(f"HTML:     {summary.html_report}")
    if summary.allure_report_dir and (summary.allure_report_dir / "index.html").is_file():
        log(f"Allure:   {summary.allure_report_dir}")
    if summary.allure_archive_dir:
        log(f"Allure archive: {summary.allure_archive_dir}")
    if summary.allure_error:
        log(f"Allure error: {summary.allure_error}")
    return exit_code == 0, summary


def _should_log_run_line(line: str) -> bool:
    """Prefer description lines from our plugin; keep failures/tracebacks."""
    s = line.strip()
    if not s:
        return False
    if s.startswith(">>>") or s.startswith("[PASSED]") or s.startswith("[FAILED]"):
        return True
    if s.startswith("[SKIPPED]") or s.startswith("[ERROR]") or s.startswith("[XFAIL]"):
        return True
    if s.startswith("E ") or s.startswith(">") or "Error" in s or "Exception" in s:
        return True
    lower = s.lower()
    if "passed" in lower and ("failed" in lower or "skipped" in lower or " in " in lower):
        return True
    if s.startswith("=== Summary") or s.startswith("Selected:") or s.startswith("Passed:"):
        return True
    if s.startswith("Failed:") or s.startswith("Skipped:") or s.startswith("Errors:") or s.startswith("HTML:"):
        return True
    if s.startswith("Allure:") or s.startswith("Allure "):
        return True
    if s.startswith("FAILED ") or s.startswith("ERROR ") or s.startswith("PASSED "):
        return False
    if "::" in s and s.startswith("tests/"):
        return False
    if "drone ws discovery" in lower or "drone auto-discovery" in lower:
        return False
    if s.startswith("Running ") or s.startswith("HEADLESS=") or s.startswith("Reports "):
        return True
    return False


def _fill_summary_from_junit(summary: TestRunSummary, junit_path: Path) -> None:
    try:
        root = ET.parse(junit_path).getroot()
    except (OSError, ET.ParseError):
        return

    suites = root.findall("testsuite")
    if root.tag == "testsuite":
        suites = [root]

    for suite in suites:
        for case in suite.findall("testcase"):
            classname = case.attrib.get("classname", "").replace(".", "/")
            name = case.attrib.get("name", "")
            nodeid = f"{classname}.py::{name}" if classname and name else name
            # Prefer file path style if classname already looks like path
            if "/" in classname or classname.startswith("tests"):
                nodeid = f"{classname}::{name}" if name else classname

            failure = case.find("failure")
            error = case.find("error")
            skipped = case.find("skipped")
            if failure is not None:
                outcome = "failed"
                message = (failure.attrib.get("message") or failure.text or "").strip()
                summary.failed += 1
            elif error is not None:
                outcome = "error"
                message = (error.attrib.get("message") or error.text or "").strip()
                summary.errors += 1
            elif skipped is not None:
                outcome = "skipped"
                message = (skipped.attrib.get("message") or skipped.text or "").strip()
                summary.skipped += 1
            else:
                outcome = "passed"
                message = ""
                summary.passed += 1

            summary.cases.append(TestCaseResult(nodeid=nodeid, outcome=outcome, message=message))
