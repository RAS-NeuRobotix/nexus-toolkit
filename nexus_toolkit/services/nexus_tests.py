"""Discover, update, and run Nexus automated tests (nexus-tests repo)."""

from __future__ import annotations

import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.request import urlopen

from nexus_toolkit.paths import LOGS_DIR, NEXUS_TESTS_DIR, NEXUS_TESTS_GIT

DEFAULT_NEXUS_TESTS_DIR = NEXUS_TESTS_DIR
DEFAULT_NEXUS_TESTS_GIT = NEXUS_TESTS_GIT
DEFAULT_VITE_URL = "http://localhost:5173"
TOOLKIT_TEST_RUNS_DIR = LOGS_DIR / "test-runs"

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
    cases: list[TestCaseResult] = field(default_factory=list)
    command: str = ""

    @property
    def total_executed(self) -> int:
        return self.passed + self.failed + self.skipped + self.errors


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
class TestDisplayInfo:
    """Human-readable parts derived from a pytest nodeid."""

    nodeid: str
    kind: str  # API, E2E, Performance, …
    group: str  # e.g. "API · nfz"
    title: str  # short readable test name
    module: str  # file stem without test_ prefix


def parse_test_display(nodeid: str) -> TestDisplayInfo:
    """Turn ``tests/api/nfz/test_nfz_api.py::test_foo[bar]`` into clear UI labels."""
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

    title = _humanize_test_function(func_part or module_stem or nodeid)
    return TestDisplayInfo(
        nodeid=nodeid,
        kind=kind,
        group=group,
        title=title,
        module=module_stem,
    )


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
) -> tuple[bool, list[str], str]:
    """Return pytest nodeids via --collect-only."""
    log = on_line or (lambda _msg: None)
    ok, message = ensure_repo_dir(repo_dir)
    if not ok:
        return False, [], message

    run_dir = _writable_run_dir()
    collect_log = run_dir / "collect.log"

    python = resolve_tests_python(repo_dir)
    cmd = [
        *python,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
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

    log("Running: " + " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=180,
        env=_pytest_env({"HEADLESS": "true"}),
    )
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    for line in combined.splitlines():
        if line.strip():
            log(line)

    nodeids = _parse_collect_nodeids(result.stdout or "")
    if result.returncode not in (0, 5) and not nodeids:
        # 5 = no tests collected
        return False, [], (result.stderr or result.stdout or "collect failed").strip()
    return True, nodeids, f"Collected {len(nodeids)} tests"


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
        allure_dir = repo_dir / "allure-results"
        try:
            allure_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        cmd.extend(["--alluredir", str(allure_dir)])

    cmd.extend(selected_nodeids)

    env = _pytest_env({"HEADLESS": "true" if options.headless else "false"})

    summary.command = " ".join(cmd)
    log("Running: " + summary.command)
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
        log(line.rstrip("\n"))
    exit_code = process.wait()
    summary.exit_code = exit_code

    if junit_report.is_file():
        _fill_summary_from_junit(summary, junit_report)
    else:
        log("JUnit report missing — summary counts may be incomplete")

    log("")
    log("=== Summary ===")
    log(f"Selected: {summary.selected_count}")
    log(f"Passed:   {summary.passed}")
    log(f"Failed:   {summary.failed}")
    log(f"Skipped:  {summary.skipped}")
    log(f"Errors:   {summary.errors}")
    if summary.html_report and summary.html_report.is_file():
        log(f"HTML:     {summary.html_report}")
    return exit_code == 0, summary


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
