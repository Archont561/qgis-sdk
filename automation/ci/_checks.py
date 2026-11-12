from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ._commands import (
    LTS_MODULES,
    LTS_PROBE,
    ROOT,
    annotation,
    check_generated_facts1,
    lts_command,
    run_logged,
    status_code,
)


def _lts_probe() -> tuple[str | None, int]:
    """Prove the QGIS Server bindings and return the host facts line."""
    probe = subprocess.run(
        [sys.executable, "-c", LTS_PROBE],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        check=False,
    )
    if probe.returncode or "qgisserver" not in probe.stdout:
        annotation(
            "LTS host: no QGIS Server in this build",
            "\n".join(probe.stdout.splitlines()[-20:]),
        )
        print(
            "::error title=LTS host::This QGIS has no qgis.server. Install "
            "qgis, qgis-server and python3-qgis from a repository that builds "
            "WITH_SERVER=ON; conda-forge builds QGIS without it."
        )
        return None, status_code(probe.returncode) or 1
    return " | ".join(line for line in probe.stdout.splitlines() if line), 0


def lts(command: list[str] | None = None) -> int:
    """Prove this QGIS has both hosts, then run each LTS module on its own.

    QGIS 3.44 LTS is what Debian and Ubuntu install and it is a Qt 5 build: a
    missing ``qgis.server`` means the row installed a QGIS without server
    bindings - conda-forge has none - and a failed ``qgis.core`` import means
    the packages are not there at all. Both are reported before pytest runs,
    because a suite that skips every test would otherwise read as a pass
    (TASK-80, decision-70).

    A module that reports skipped tests fails the row: on this build nothing
    may skip, or the host it was meant to prove was not proven.
    """
    facts, refused = _lts_probe()
    if facts is None:
        return refused
    print(f"::notice::LTS host: {facts}")
    if command:  # an explicit command replaces the module loop
        return _lts_run(command, Path("lts-host.log"))
    status = 0
    for module in LTS_MODULES:
        status = _lts_run(lts_command(module), Path("lts") / f"{module}.log") or status
    return status


def _lts_run(command: list[str], log: Path) -> int:
    """Run one LTS module and refuse a result that proved nothing."""
    log.parent.mkdir(parents=True, exist_ok=True)
    status = run_logged(command, log)
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    summary = [
        line for line in text.splitlines() if " passed" in line or " failed" in line
    ]
    module = next((word for word in command if word.endswith(".py")), "the LTS row")
    if status == 5 or "no tests ran" in text:
        annotation(f"LTS host: {module} collected nothing", text[-2000:])
        print(
            f"::error title=LTS host::{module} collected no tests; the row is "
            "not proving anything."
        )
        return 1
    if " skipped" in " ".join(summary):
        annotation(f"LTS host: {module} skipped", "\n".join(text.splitlines()[-30:]))
        print(
            f"::error title=LTS host::{module} skipped tests on a build that has "
            "both hosts; the Desktop or server half was not proven."
        )
        return 1
    if summary:
        print(f"::notice::LTS host: {summary[-1].strip()} ({module})")
    if status:
        annotation("LTS host: pytest", "\n".join(text.splitlines()[-60:]))
    return status


def _generate_bridge_clients() -> int:
    """Regenerate the TypeScript bridge clients; explain a failed generator."""
    generator = "packages/qgis-sdk-python/scripts/generate_bridge_clients.py"
    code = subprocess.run([sys.executable, generator], cwd=ROOT, check=False).returncode
    if code:
        print(
            "::error title=generated client is stale::Bridge generation failed. "
            "Review the generator output, remove any reported orphan or restore it "
            "to artifacts(), and commit regenerated files."
        )
    return status_code(code)


def check_generated() -> int:
    code = _generate_bridge_clients()
    if code:
        return code
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", "packages/qgis-sdk-typescript"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode:
        sys.stderr.write(status.stderr)
        return status_code(status.returncode)
    if status.stdout:
        subprocess.run(
            ["git", "--no-pager", "diff", "--", "packages/qgis-sdk-typescript"],
            cwd=ROOT,
            check=False,
        )
        print(
            "::error title=generated client is stale::Run `python packages/qgis-sdk-python/scripts/generate_bridge_clients.py` and commit the result."
        )
        return 1
    return check_generated_facts1()


FEATURE_DIRECTORIES = ("packages/qgis-sdk-python/tests/features",)
GHERLINIT_FINDING = re.compile(r"^\S+\.feature:\d+:\d+:")


def feature_files(root: Path = ROOT) -> list[Path]:
    """Every feature file in the checkout, in a stable order."""
    return sorted(
        path
        for path in root.rglob("*.feature")
        if not {"node_modules", ".git", "dist", "build"} & set(path.parts)
    )


def unlinted_features(root: Path = ROOT) -> list[Path]:
    """The feature files that sit outside :data:`FEATURE_DIRECTORIES`."""
    covered = [(root / directory).resolve() for directory in FEATURE_DIRECTORIES]
    return [
        path
        for path in feature_files(root)
        if not any(path.resolve().is_relative_to(directory) for directory in covered)
    ]


def _gherlint(executable: str | None) -> str | None:
    """Find the linter: an explicit path, or the one on ``PATH``."""
    if executable:
        return executable if Path(executable).exists() else None
    return shutil.which("gherlint")


def _gherkin_guard(executable: str | None, root: Path) -> tuple[str | None, int | None]:
    """Answer whether the check can run, as ``(tool, status)``.

    Every way the lint cannot mean anything is a guard here: an unlinted feature
    file, a checkout with no features, a linter that is not installed. The check
    itself keeps a single shape for the one case it is for.
    """
    stray = unlinted_features(root)
    if stray:
        for path in stray:
            print(f"{path.relative_to(root)} is outside the linted directories")
        print(
            "::error title=feature file outside the lint::Add its directory to "
            "FEATURE_DIRECTORIES in automation/ci.py so every scenario is linted."
        )
        return None, 1
    if not feature_files(root):
        print(
            "::error title=no feature files::The checkout has no *.feature file to lint."
        )
        return None, 1
    tool = _gherlint(executable)
    if tool is None:
        print(
            "::error title=gherlint is missing::Install the linter "
            "(`pip install gherlint==0.5.0`, or the `bdd` extra) and re-run. Its "
            "pydantic 1 dependency is why it is not part of the runtime's dev extra."
        )
        return None, 127
    return tool, None


def _lint_directory(tool: str, target: Path, root: Path) -> tuple[int, str]:
    """Lint one directory and hand back the linter's status and output."""
    result = subprocess.run(
        [tool, "lint", str(target)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def _report_findings(findings: list[str], root: Path) -> int:
    """Print the linter's findings as annotations and answer the check."""
    if findings:
        for line in findings:
            print(line)
        print(
            f"::error title=gherlint findings::{len(findings)} finding(s) across "
            f"{len(FEATURE_DIRECTORIES)} feature directorie(s); gherlint lists "
            "code and message per line."
        )
        return 1
    print(f"gherlint: {len(feature_files(root))} feature file(s) clean")
    return 0


def _lint_feature_directories(tool: str, root: Path) -> int:
    """Lint each known directory and collect what the linter says."""
    findings: list[str] = []
    for directory in FEATURE_DIRECTORIES:
        target = root / directory
        if not target.is_dir():
            continue
        code, output = _lint_directory(tool, target, root)
        if code:
            sys.stdout.write(output)
            print(
                f"::error title=gherlint failed::gherlint exited with "
                f"{code} on {directory}."
            )
            return status_code(code)
        findings.extend(
            line for line in output.splitlines() if GHERLINIT_FINDING.match(line)
        )
    return _report_findings(findings, root)


def check_gherkin(executable: str | None = None, root: Path = ROOT) -> int:
    """Lint every feature file with gherlint; one finding is a failure.

    ``gherlint`` pins pydantic 1, which cannot share an environment with the
    runtime's ``mcp`` extra, so CI installs it into a venv of its own and passes
    the executable here. A missing linter is reported as a missing tool rather
    than passing, because a check that silently runs nothing is worse than none.
    """
    tool, status = _gherkin_guard(executable, root)
    if tool is None:
        return status or 1
    return _lint_feature_directories(tool, root)


STREAMED_ACTIONS = ("run-log", "native", "lts", "reference-example")
"""The actions whose remaining arguments are a command to run and log."""
FATAL_MARKERS = ("Fatal Python error", "Segmentation fault")
"""What an aborted pytest prints before it dies.

Such a run has no summary line and no ``FAILED`` line: the interpreter stops
mid-test, and the only thing that says where is the C-level stack pytest's
``faulthandler`` prints after the marker. A red coverage job that reports
nothing but ``exit code 137`` costs a rerun to diagnose, so the lines under the
marker are annotated too.
"""


def annotate_coverage(log: Path) -> None:
    if not log.exists():
        return
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    pattern = re.compile(r"FAILED|ERROR|Error|error:|Coverage|TOTAL|no tests ran")
    matches = [
        f"{index}:{line}" for index, line in enumerate(lines, 1) if pattern.search(line)
    ]
    fatal = next(
        (
            index
            for index, line in enumerate(lines)
            if any(marker in line for marker in FATAL_MARKERS)
        ),
        None,
    )
    if fatal is not None:
        # An annotations cap exists per step and it keeps the first ones, so a
        # crash is reported alone and from the marker down: the frames under it
        # name the test and the C call that died, and the lines the pattern
        # above matched are an aftermath of the same death.
        for offset, line in enumerate(lines[fatal : fatal + 10], fatal + 1):
            print(f"::error title=interpreter died::{f'{offset}:{line}'[:900]}")
        return
    for line in matches[-40:]:
        print(f"::error::{line[:900]}")


def annotate_log(
    log: Path, title: str, tail: int = 25, skip_missing: bool = False
) -> None:
    """Surface the tail of a captured step log as annotations.

    A job's own log is not always reachable from a client, and "process
    completed with exit code 1" names nothing. The last lines of the step that
    failed usually do, so a failed build repeats them where a caller can read
    them. ``skip_missing`` lets one step annotate several logs, only the ones
    that exist: a run that never reached a step has no log, and a "no log at"
    annotation for it is noise in the report of the step that did fail.
    """
    if not log.exists():
        if not skip_missing:
            annotation(title, f"no log at {log}")
        return
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in [line for line in lines if line.strip()][-tail:]:
        print(f"::error title={title}::{line[:900]}")


def report_bun(log: Path, title: str) -> None:
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    summary = re.search(r"[0-9]+ pass", text)
    print(f"::notice::{title}: {summary.group() if summary else 'no summary line'}")


def report_steps() -> None:
    steps = json.loads(os.environ["STEPS"])
    for name, info in steps.items():
        if info.get("conclusion") not in ("success", "skipped", None):
            print(f"::error title=failed step::{name}")


def bun_ui() -> int:
    for package in ("@archont561/qgis-sdk", "@archont561/qgis-sdk-ui"):
        status = subprocess.run(
            ["bun", "run", "--filter", package, "build"], check=False
        ).returncode
        if status:
            return status_code(status)
    return run_logged(
        [
            "bun",
            "test",
            "--conditions=browser",
            "packages/qgis-sdk-ui/tests",
            "packages/qgis-sdk-ui-alias/tests",
        ],
        Path("bun-ui-tests.log"),
    )
