"""CI workflow helpers: run gates and report their results without shell pipelines.

The commands here preserve the workflow's exit statuses and annotations. They
are stdlib-only so the cross-platform jobs can run them with setup-python.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


def _reference_example_tail1(**values):
    runs = values["runs"]
    status = values["status"]
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


def _add_report_parsers(commands) -> None:
    """Declare the parsers whose only job is turning a log into annotations."""
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


def _dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Run the one action argparse selected, or report on a log."""
    from ._checks import STREAMED_ACTIONS, bun_ui, check_generated, check_gherkin
    from ._main import report, streamed

    if args.action in STREAMED_ACTIONS:
        return streamed(args, parser)
    if args.action == "check-generated":
        return check_generated()
    if args.action == "check-gherkin":
        return check_gherkin(args.gherlint, args.root)
    if args.action == "bun-ui":
        return bun_ui()
    report(args)
    return 0


def main_tail1(**values):
    argv = values["argv"]
    parser = values["parser"]
    _add_report_parsers(values["commands"])
    return _dispatch(parser.parse_args(argv), parser)


def check_generated_facts1():
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


ROOT = Path(__file__).resolve().parent.parent.parent
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


def abort_at(text: str) -> int:
    """Where a Qt abort starts its own faulthandler dump, or the end of the log."""
    found = text.find("Fatal Python error")
    return len(text) if found == -1 else found


def before_abort(text: str, lines: int = 120) -> str:
    """The log up to a Qt abort, which ends the process with a long dump of its own.

    Taken from the tail, the window would show only C frames: the test that was
    running appears just before the dump, not inside it.
    """
    return text[: abort_at(text)]


def native(command: list[str]) -> int:
    # Unbuffered, because a Qt abort ends the process wherever it is: behind a
    # block buffer the log stops thousands of bytes short of the test that was
    # running, and the annotation below then names the wrong one.
    os.environ["PYTHONUNBUFFERED"] = "1"
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
    diagnose(text)
    return status


def diagnose(text: str) -> None:
    """Annotate a failed native run: what failed, where, and on what host.

    The four windows answer different questions and a Qt abort needs all of
    them: ``failures()`` reads the short summary, :func:`before_abort` the
    progress line before the dump, :func:`abort_at` the frames inside it, and the
    probe what QGIS and Qt the runner actually had.
    """
    named = failures(text)
    if named:
        annotation(f"native layers: {len(named)} failed", "\n".join(named))
    probe = subprocess.run(
        [sys.executable, "-c", ENVIRONMENT_PROBE],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        check=False,
    )
    annotation("native layers: environment", "\n".join(probe.stdout.splitlines()[-20:]))
    annotation(
        "native layers: pytest", "\n".join(before_abort(text).splitlines()[-120:])
    )
    at = abort_at(text)
    if at < len(text):
        # The frame that aborted is in the first lines of the dump; its tail is
        # only C addresses.
        annotation("native layers: abort", "\n".join(text[at:].splitlines()[:60]))


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
    return _reference_example_tail1(**{**globals(), **locals()})


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
