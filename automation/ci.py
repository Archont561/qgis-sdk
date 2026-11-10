#!/usr/bin/env python3
"""CI workflow helpers: run gates and report their results without shell pipelines.

The commands here preserve the workflow's exit statuses and annotations. They
are stdlib-only so the cross-platform jobs can run them with setup-python.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NATIVE_COMMAND = [
    "pixi",
    "run",
    "-e",
    "default",
    "python",
    "-m",
    "pytest",
    "-c",
    "packages/qgis-sdk-python/pyproject.toml",
    "packages/qgis-sdk-python/tests",
    "-m",
    "native and not smoke",
    "-q",
    # `-q` on its own prints no short summary, and `-rs` asks for skips alone:
    # a job with twenty failures then names none of them. `-rfE` puts the failed
    # and errored test ids in the log, which is what `native()` annotates and
    # what a rerun otherwise has to rediscover.
    "-rfEs",
    # TEMPORARY diagnostic: name the test a Qt abort kills, since an abort
    # leaves no summary for `failures()` to read.
    "-v",
]
LTS_PROBE = (
    "import qgis.core, qgis.server; "
    "print('qgis', qgis.core.Qgis.version()); "
    "print('qgisserver', qgis.server.QgsServer.__name__); "
    "import qgis.PyQt.QtCore as qt; "
    "print('qt', qt.QT_VERSION_STR); "
    "print('binding', 'PyQt' + qt.QT_VERSION_STR.split('.')[0])"
)
LTS_TESTS = "packages/qgis-sdk-python/tests"
LTS_MODULES = (
    "test_server_native.py",
    "test_lts_native.py",
    "test_server_devtools_native.py",
)
ENVIRONMENT_PROBE = (
    'import sys, pathlib; sys.path.insert(0, str(pathlib.Path(sys.prefix) / "share" / "qgis" / "python")); '
    "print(sys.version); import PyQt6, qgis.core; print(PyQt6.__file__); print(qgis.core.Qgis.version())"
)


def status_code(code: int) -> int:
    """Return the status a shell pipeline would expose for a signalled process."""
    return 128 - code if code < 0 else code


def emit(chunk: bytes) -> None:
    """Write ``chunk`` to this process's stdout, which may not be a file.

    doit replaces ``sys.stdout`` with a wrapper that captures a task's output, and
    that wrapper has no ``buffer``. Writing to ``sys.stdout.buffer`` works in a
    shell and raises ``AttributeError`` under the runner, so the bytes go through
    whichever of the two is there.
    """
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        sys.stdout.write(chunk.decode("utf-8", errors="replace"))
    else:
        buffer.write(chunk)
    sys.stdout.flush()


def run_logged(command: list[str], log: Path) -> int:
    """Stream combined stdout and stderr to the job log and a file, like tee."""
    with log.open("wb") as output:
        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
        except (FileNotFoundError, PermissionError) as exc:
            message = f"{command[0]}: {exc.strerror}\n".encode(
                "utf-8", errors="replace"
            )
            output.write(message)
            emit(message)
            return 127 if isinstance(exc, FileNotFoundError) else 126
        assert process.stdout is not None
        while chunk := process.stdout.read1(65536):
            output.write(chunk)
            output.flush()
            emit(chunk)
        return status_code(process.wait())


def annotation(title: str, text: str) -> None:
    body = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::error title={title}::{body}")


def failures(text: str, limit: int = 60) -> list[str]:
    """The ``FAILED`` lines of a pytest run, without the assertion bodies.

    The tail of a native run is the last few tracebacks, so a job with twenty
    failures costs a rerun per failure: the annotation cap keeps the first ones
    and the ones that stay readable are the ones nobody needed. The summary block
    pytest prints at the end names every test that failed, which is the part to
    surface first.
    """
    named = [
        line.strip()
        for line in text.splitlines()
        if line.startswith(("FAILED ", "ERROR "))
    ]
    return named[:limit]


def native(command: list[str]) -> int:
    log = Path("native-layers.log")
    status = run_logged(command, log)
    if status == 0:
        return 0
    # The workflow's original diagnostics stripped carriage returns before
    # creating annotations, rather than treating them as new lines.
    text = log.read_bytes().decode("utf-8", errors="replace").replace("\r", "")
    reason = re.search(
        r"native (?:forms|networking|WebEngine|WebChannel|jobs) need[^\n]*", text
    )
    if status == 5 and reason:
        print(f"::warning::native layers did not run: {reason.group()}")
        return 0
    probe = subprocess.run(
        [sys.executable, "-c", ENVIRONMENT_PROBE],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        check=False,
    )
    named = failures(text)
    if named:
        annotation(f"native layers: {len(named)} failed", "\n".join(named))
    annotation("native layers: environment", "\n".join(probe.stdout.splitlines()[-20:]))
    annotation("native layers: pytest", "\n".join(text.splitlines()[-60:]))
    return status


#: The reference projects' own suites, one run each: the pure target of
#: ``examples/simple``, its ``qgis`` target, then ``examples/server``. The three
#: used to be one ``&&`` chain in the Pixi task, which meant a failing pure run
#: hid whether the native half passed and the job reported "exit code 1" without
#: naming a test.
REFERENCE_EXAMPLE_RUNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("simple-pure", ("--project", "examples/simple")),
    ("simple-qgis", ("--project", "examples/simple", "--target", "qgis")),
    ("server-pure", ("--project", "examples/server")),
)
REFERENCE_EXAMPLE_LOGS = Path("reference-example")


def reference_example_command(arguments: tuple[str, ...]) -> list[str]:
    """The ``qgis-sdk test`` invocation for one reference-project run.

    ``-rfEs`` for the same reason ``NATIVE_COMMAND`` carries it: ``-q`` alone
    prints no short summary, so the log the annotation reads would name nothing.
    """
    return [
        sys.executable,
        "-m",
        "qgis_sdk_tools",
        "test",
        *arguments,
        "-q",
        "-rfEs",
    ]


def reference_example(command: list[str] | None = None) -> int:
    """Run each reference project's suite on its own, annotating every failure.

    An explicit ``command`` replaces the three runs, so the helper is testable
    without a reference project on disk. Every run executes even after one
    fails - a red pure target used to hide the native result - and the first
    non-zero status is the one the step reports.
    """
    runs = (
        (("override", tuple(command)),)
        if command
        else tuple(
            (label, tuple(reference_example_command(arguments)))
            for label, arguments in REFERENCE_EXAMPLE_RUNS
        )
    )
    status = 0
    REFERENCE_EXAMPLE_LOGS.mkdir(parents=True, exist_ok=True)
    for label, run in runs:
        log = REFERENCE_EXAMPLE_LOGS / f"{label}.log"
        code = run_logged(list(run), log)
        if code == 0:
            continue
        text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        # The tail is the last few tracebacks, so the summary is what names them.
        named = failures(text)
        if named:
            annotation(
                f"reference example: {label}: {len(named)} failed", "\n".join(named)
            )
        annotation(
            f"reference example: {label}: pytest",
            "\n".join(text.splitlines()[-80:]),
        )
        status = status or code
    return status


def lts_command(module: str) -> list[str]:
    """The pytest command for one LTS module, run on its own.

    One module at a time, because the row has to prove *both* hosts ran:
    ``-m`` filters after collection and a module whose import fails skips
    itself with ``importorskip``, so a single run that reports "3 passed" could
    be hiding a Desktop half that never started. One command per module makes
    that impossible to miss.
    """
    path = ROOT / LTS_TESTS / module
    if not path.is_file():
        raise FileNotFoundError(f"the LTS row names a module that is not there: {path}")
    return [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        "packages/qgis-sdk-python/pyproject.toml",
        str(path.relative_to(ROOT)),
        "-q",
        "-rs",
    ]


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
        return status_code(probe.returncode) or 1
    facts = " | ".join(line for line in probe.stdout.splitlines() if line)
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


def check_generated() -> int:
    generator = "packages/qgis-sdk-python/scripts/generate_bridge_clients.py"
    code = subprocess.run([sys.executable, generator], cwd=ROOT, check=False).returncode
    if code:
        print(
            "::error title=generated client is stale::Bridge generation failed. "
            "Review the generator output, remove any reported orphan or restore it "
            "to artifacts(), and commit regenerated files."
        )
        return status_code(code)
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
    reference = [
        "pixi",
        "run",
        "-e",
        "default",
        "python",
        "-m",
        "qgis_sdk_tools",
        "bridge",
        "generate",
        "--out",
        "web/src/bridge.schema.ts",
        "--check",
    ]
    return status_code(
        subprocess.run(reference, cwd=ROOT / "examples/simple", check=False).returncode
    )


#: Where the BDD scenarios live, relative to the checkout root. Every
#: ``*.feature`` file in the tree has to sit below one of these; a new directory
#: is a failure rather than a file that quietly stops being linted.
FEATURE_DIRECTORIES = ("packages/qgis-sdk-python/tests/features",)

#: What gherlint prints for one finding: ``<path>:<line>:<column>: <message>``.
#: The tool always exits with zero, so the findings are counted from the report
#: instead of from the status. The ``***** <path>`` headers do not match.
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    log = commands.add_parser("run-log")
    log.add_argument("log", type=Path)
    log.add_argument("command", nargs=argparse.REMAINDER)
    native_parser = commands.add_parser("native")
    native_parser.add_argument("command", nargs=argparse.REMAINDER)
    lts_parser = commands.add_parser("lts")
    lts_parser.add_argument("command", nargs=argparse.REMAINDER)
    commands.add_parser("check-generated")
    gherkin = commands.add_parser("check-gherkin")
    gherkin.add_argument(
        "--gherlint",
        default=None,
        help="the linter to run; defaults to gherlint on PATH",
    )
    gherkin.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="the checkout to lint; defaults to this script's repository",
    )
    coverage = commands.add_parser("annotate-coverage")
    coverage.add_argument("log", type=Path)
    step_log = commands.add_parser("annotate-log")
    step_log.add_argument("log", type=Path)
    step_log.add_argument("--title", default="failed step")
    step_log.add_argument("--tail", type=int, default=25)
    step_log.add_argument("--skip-missing", action="store_true")
    bun = commands.add_parser("report-bun")
    bun.add_argument("log", type=Path)
    bun.add_argument("--title", required=True)
    reference = commands.add_parser("reference-example")
    reference.add_argument("command", nargs=argparse.REMAINDER)
    commands.add_parser("report-steps")
    commands.add_parser("bun-ui")
    args = parser.parse_args(argv)
    if args.action in STREAMED_ACTIONS:
        return _streamed(args, parser)
    if args.action == "check-generated":
        return check_generated()
    if args.action == "check-gherkin":
        return check_gherkin(args.gherlint, args.root)
    if args.action == "bun-ui":
        return bun_ui()
    _report(args)
    return 0


def _streamed(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Run one of the actions whose command is forwarded to a subprocess."""
    command = _after_separator(args.command)
    if args.action == "native":
        return native(command or NATIVE_COMMAND)
    if args.action == "lts":
        return lts(command)
    if args.action == "reference-example":
        return reference_example(command)
    if not command:
        parser.error("run-log requires a command after --")
    return run_logged(command, args.log)


def _after_separator(command: list[str]) -> list[str]:
    """Drop the ``--`` argparse leaves in front of a forwarded command."""
    return command[1:] if command and command[0] == "--" else command


def _report(args: argparse.Namespace) -> None:
    """Turn a step's log into annotations; these report, they do not gate."""
    if args.action == "annotate-coverage":
        annotate_coverage(args.log)
    elif args.action == "annotate-log":
        annotate_log(args.log, args.title, args.tail, args.skip_missing)
    elif args.action == "report-bun":
        report_bun(args.log, args.title)
    elif args.action == "report-steps":
        report_steps()


if __name__ == "__main__":
    sys.exit(main())
