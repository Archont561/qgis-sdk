#!/usr/bin/env python3
"""Watch a pull request's CI: poll every 15 seconds, break on the first error.

``gh pr checks --watch`` waits for every check to finish before it answers, so
a job that fails in the first minute still costs the whole run. This watcher
answers as soon as any check fails, while the rest are still queued or
running, and answers success only when nothing is left pending.

    python -m automation.pr --pr 211
    python -m automation.pr --pr 211 --interval 15 --timeout 600
    python -m automation.pr  # the pull request of the current branch

Exit status: 0 when every check passed, 1 when a check failed (the wait
breaks, the remote run is not cancelled), 2 on timeout, 127 when ``gh``
itself kept failing. The tool is stdlib-only and independently runnable.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass

#: Conclusions that mean the check failed. A completed check with any other
#: conclusion is not a failure; one outside both sets is still pending.
FAILED_CONCLUSIONS = frozenset(
    {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STALE", "STARTUP_FAILURE"}
)
PASSED_CONCLUSIONS = frozenset({"SUCCESS", "SKIPPED", "NEUTRAL"})


class QgisSdkPrError(RuntimeError):
    """``gh`` failed, or answered with something this watcher cannot read."""


@dataclass(frozen=True)
class Check:
    """One check of a pull request, as ``statusCheckRollup`` reports it."""

    name: str
    status: str
    conclusion: str | None


@dataclass(frozen=True)
class Snapshot:
    """Every check of one pull request at one moment."""

    pr: int
    state: str
    checks: tuple[Check, ...]

    @property
    def failed(self) -> tuple[Check, ...]:
        return tuple(
            check
            for check in self.checks
            if check.status == "COMPLETED" and check.conclusion in FAILED_CONCLUSIONS
        )

    @property
    def pending(self) -> tuple[Check, ...]:
        return tuple(
            check
            for check in self.checks
            if check.status != "COMPLETED"
            or check.conclusion not in FAILED_CONCLUSIONS | PASSED_CONCLUSIONS
        )

    @property
    def passed(self) -> tuple[Check, ...]:
        return tuple(
            check
            for check in self.checks
            if check.status == "COMPLETED" and check.conclusion in PASSED_CONCLUSIONS
        )


def run_gh(arguments: list[str]) -> str:
    """Run ``gh`` and hand back its stdout, or raise with its stderr."""
    completed = subprocess.run(
        ["gh", *arguments], capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise QgisSdkPrError(
            f"gh {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout


def fetch(pr: int, repo: str = "") -> Snapshot:
    """Read one pull request's checks through ``gh pr view``."""
    arguments = ["pr", "view", str(pr), "--json", "statusCheckRollup,state"]
    if repo:
        arguments.extend(["--repo", repo])
    try:
        data = json.loads(run_gh(arguments))
        checks = tuple(
            Check(
                name=item["name"],
                status=item["status"],
                conclusion=item.get("conclusion"),
            )
            for item in data["statusCheckRollup"]
        )
        return Snapshot(pr=pr, state=data["state"], checks=checks)
    except (ValueError, KeyError, TypeError) as exc:
        raise QgisSdkPrError(f"gh answered unexpectedly for PR #{pr}") from exc


def resolve_pr(repo: str = "") -> int:
    """The pull request of the current branch, through ``gh pr view``."""
    arguments = ["pr", "view", "--json", "number"]
    if repo:
        arguments.extend(["--repo", repo])
    try:
        return int(json.loads(run_gh(arguments))["number"])
    except (ValueError, KeyError, TypeError) as exc:
        raise QgisSdkPrError("no pull request for the current branch") from exc


def sleep(seconds: float) -> None:
    """Wait between polls; a seam so tests never wait."""
    time.sleep(seconds)


def monotonic() -> float:
    """The clock the timeout reads; a seam so tests never wait."""
    return time.monotonic()


def _report(snapshot: Snapshot, polls: int) -> None:
    print(
        f"pr #{snapshot.pr}: {len(snapshot.passed)} passed, "
        f"{len(snapshot.pending)} pending, {len(snapshot.failed)} failed "
        f"(poll {polls})",
        flush=True,
    )


def _report_failed(snapshot: Snapshot) -> None:
    print(
        f"pr #{snapshot.pr}: CI error, breaking without waiting for the rest:",
        flush=True,
    )
    for check in snapshot.failed:
        print(f"  {check.name}: {check.conclusion}", flush=True)


def _poll(number: int, repo: str, polls: int, errors: int) -> tuple[int | None, int]:
    """One poll; None keeps waiting, otherwise the exit status."""
    try:
        snapshot = fetch(number, repo)
    except QgisSdkPrError as exc:
        errors += 1
        print(f"pr #{number}: gh failed ({exc}) [{errors}/3]", flush=True)
        return (127, errors) if errors >= 3 else (None, errors)
    _report(snapshot, polls)
    if snapshot.failed:
        _report_failed(snapshot)
        return 1, 0
    if not snapshot.pending:
        print(f"pr #{number}: all checks green", flush=True)
        return 0, 0
    return None, 0


def watch(pr: int = 0, interval: int = 15, timeout: int = 0, repo: str = "") -> int:
    """Poll one pull request until it passes, fails, or times out."""
    try:
        number = resolve_pr(repo) if pr == 0 else pr
    except QgisSdkPrError as exc:
        print(f"pr watch: {exc}", flush=True)
        return 127
    deadline = monotonic() + timeout if timeout > 0 else None
    errors = 0
    polls = 0
    while True:
        polls += 1
        status, errors = _poll(number, repo, polls, errors)
        if status is not None:
            return status
        if deadline is not None and monotonic() >= deadline:
            print(f"pr #{number}: timed out after {timeout}s", flush=True)
            return 2
        sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pr",
        type=int,
        default=0,
        help="pull request number; 0 is the current branch's",
    )
    parser.add_argument(
        "--interval", type=int, default=15, help="seconds between polls"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="give up after this many seconds; 0 waits forever",
    )
    parser.add_argument(
        "--repo", default="", help="owner/name; defaults to this checkout"
    )
    args = parser.parse_args(argv)
    return watch(
        pr=args.pr, interval=args.interval, timeout=args.timeout, repo=args.repo
    )


if __name__ == "__main__":
    sys.exit(main())
