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
    "-rs",
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
LTS_MODULES = ("test_server_native.py", "test_lts_native.py")
ENVIRONMENT_PROBE = (
    'import sys, pathlib; sys.path.insert(0, str(pathlib.Path(sys.prefix) / "share" / "qgis" / "python")); '
    "print(sys.version); import PyQt6, qgis.core; print(PyQt6.__file__); print(qgis.core.Qgis.version())"
)


def status_code(code: int) -> int:
    """Return the status a shell pipeline would expose for a signalled process."""
    return 128 - code if code < 0 else code


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
            sys.stdout.buffer.write(message)
            sys.stdout.buffer.flush()
            return 127 if isinstance(exc, FileNotFoundError) else 126
        assert process.stdout is not None
        while chunk := process.stdout.read1(65536):
            output.write(chunk)
            output.flush()
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
        return status_code(process.wait())


def annotation(title: str, text: str) -> None:
    body = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::error title={title}::{body}")


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
    annotation("native layers: environment", "\n".join(probe.stdout.splitlines()[-20:]))
    annotation("native layers: pytest", "\n".join(text.splitlines()[-60:]))
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


def annotate_coverage(log: Path) -> None:
    if not log.exists():
        return
    pattern = re.compile(r"FAILED|ERROR|Error|error:|Coverage|TOTAL|no tests ran")
    matches = [
        f"{index}:{line}"
        for index, line in enumerate(
            log.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        )
        if pattern.search(line)
    ]
    for line in matches[-40:]:
        print(f"::error::{line[:900]}")


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
    coverage = commands.add_parser("annotate-coverage")
    coverage.add_argument("log", type=Path)
    bun = commands.add_parser("report-bun")
    bun.add_argument("log", type=Path)
    bun.add_argument("--title", required=True)
    commands.add_parser("report-steps")
    commands.add_parser("bun-ui")
    args = parser.parse_args(argv)
    if args.action in ("run-log", "native", "lts"):
        command = args.command
        if command and command[0] == "--":
            command = command[1:]
        if args.action == "native":
            return native(command or NATIVE_COMMAND)
        if args.action == "lts":
            return lts(command)
        if not command:
            parser.error("run-log requires a command after --")
        return run_logged(command, args.log)
    if args.action == "check-generated":
        return check_generated()
    if args.action == "annotate-coverage":
        annotate_coverage(args.log)
    elif args.action == "report-bun":
        report_bun(args.log, args.title)
    elif args.action == "report-steps":
        report_steps()
    elif args.action == "bun-ui":
        return bun_ui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
