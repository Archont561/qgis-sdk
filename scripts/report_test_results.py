#!/usr/bin/env python3
"""Report JUnit test results as GitHub annotations and a step summary.

Extracted from ci.yml's cross-platform job so the same reporting logic runs
in CI and can be validated locally:

    pixi run -e default python scripts/report_test_results.py python-tests.xml
    python scripts/report_test_results.py bun-tests.log --title "bun test"

Usage:
    report_test_results.py <junit-xml> [--title <title>] [--fail-on-error]
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def find_problem(case):
    """Return the failure or error node of one JUnit test case."""
    problem = case.find("failure")
    return case.find("error") if problem is None else problem


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Report JUnit test results as GitHub annotations."
    )
    parser.add_argument("report", help="Path to the JUnit XML report.")
    parser.add_argument(
        "--title",
        default="pytest",
        help="Test suite name used in the step-summary notice.",
    )
    args = parser.parse_args(argv)

    report = Path(args.report)
    if not report.exists():
        print(f"::error::{args.title} did not write {report}")
        return 0

    try:
        cases = list(ET.parse(report).iter("testcase"))
    except ET.ParseError as exc:
        print(f"::error::failed to parse {report}: {exc}")
        return 1

    failures = [case for case in cases if find_problem(case) is not None]
    skipped = [case for case in cases if case.find("skipped") is not None]

    print(
        f"::notice::{args.title}: {len(cases)} collected, "
        f"{len(failures)} failed, {len(skipped)} skipped"
    )

    for case in failures:
        problem = find_problem(case)
        detail = (problem.get("message") or problem.text or "failed").strip()
        first = detail.splitlines()[0][:600]
        print(
            f"::error file={case.get('file')}::"
            f"{case.get('classname')}::{case.get('name')}: {first}"
        )

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
