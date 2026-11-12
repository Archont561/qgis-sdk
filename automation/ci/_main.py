"""Command dispatch for ``python -m automation.ci``.

One subparser per verb, and no behaviour of its own: the verbs that gate live in
``_checks``, the ones that shell out live in ``_commands``, and this module only
parses arguments and hands the namespace over. ``__main__.py`` is the entry
point that turns :func:`main` into an exit status.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ._checks import annotate_coverage, annotate_log, lts, report_bun, report_steps
from ._commands import (
    NATIVE_COMMAND,
    ROOT,
    main_tail1,
    native,
    reference_example,
    run_logged,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="automation.ci", description=__doc__)
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
    return main_tail1(**{**globals(), **locals()})


def streamed(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
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


def report(args: argparse.Namespace) -> None:
    """Turn a step's log into annotations; these report, they do not gate."""
    if args.action == "annotate-coverage":
        annotate_coverage(args.log)
    elif args.action == "annotate-log":
        annotate_log(args.log, args.title, args.tail, args.skip_missing)
    elif args.action == "report-bun":
        report_bun(args.log, args.title)
    elif args.action == "report-steps":
        report_steps()
