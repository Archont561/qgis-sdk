#!/usr/bin/env python3
"""The one way this repository opens and watches a pull request.

``open`` pushes the branch and creates the pull request; ``watch`` polls its CI
every 15 seconds and breaks on the first error.

``gh pr checks --watch`` waits for every check to finish before it answers, so
a job that fails in the first minute still costs the whole run. This watcher
answers as soon as any check fails, while the rest are still queued or
running, and answers success only when at least one check reported and nothing
is left pending - a pull request with no check-runs yet is still waiting, not
green.

    python -m automation.pr open                    # commits decide title/body
    python -m automation.pr open --title "..." --body-file body.md
    python -m automation.pr --pr 211

A hand-written `git push` plus `gh pr create` plus `gh api -X PATCH` to repair
a body is what `open` replaces (AGENTS.md): the same steps, in the order they
belong, with the commit list as the default body.

Exit status: 0 when the pull request was created or every check passed, 1 when
`open` refuses (the branch is the base, or a pull request already exists) or a
check failed, 2 on a watch timeout, 127 when `git` or ``gh`` failed. The tool
is stdlib-only and runs without the task runner - `python -m automation.pr`,
the same way every module here is run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# The records live in a sibling module; they are re-exported here, so
# `pr.Snapshot` and `pr_records.Snapshot` stay one object (decision-84).
from automation.pr_records import (
    FAILED_CONCLUSIONS,  # noqa: F401 - re-exported: the tests parametrise over it
    PASSED_CONCLUSIONS,  # noqa: F401 - re-exported: the tests parametrise over it
    Branch,
    Check,
    PullRequestRequest,
    QgisSdkPrError,
    Snapshot,
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


def run_git(arguments: list[str]) -> str:
    """Run ``git`` and hand back its stdout, or raise with its stderr."""
    completed = subprocess.run(
        ["git", *arguments], capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise QgisSdkPrError(
            f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout


def current_branch() -> str:
    """The branch being opened; a detached HEAD has nothing to open."""
    name = run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if not name or name == "HEAD":
        raise QgisSdkPrError("detached HEAD: check out the branch to open")
    return name


def default_branch(repo: str = "") -> str:
    """The branch a pull request lands on, as GitHub names it."""
    arguments = ["repo", "view", "--json", "defaultBranchRef", "--jq"]
    arguments.append(".defaultBranchRef.name")
    if repo:
        arguments.extend(["--repo", repo])
    name = run_gh(arguments).strip()
    if not name:
        raise QgisSdkPrError("gh could not name the default branch")
    return name


def subjects(base: str) -> tuple[str, ...]:
    """The commit subjects the base branch does not have, oldest first."""
    output = run_git(["log", "--reverse", "--format=%s", f"{base}..HEAD"])
    return tuple(line for line in output.splitlines() if line.strip())


def title_for(items: tuple[str, ...]) -> str:
    """A title from the commits: the newest one speaks for the branch."""
    if not items:
        raise QgisSdkPrError("no commits against the base: nothing to open")
    return items[-1]


def body_for(items: tuple[str, ...]) -> str:
    """The default body: the commits, one per line, and nothing invented."""
    return "\n".join(f"- {item}" for item in items)


def existing(repo: str = "") -> int | None:
    """The pull request already open for this branch, if there is one."""
    try:
        return resolve_pr(repo)
    except QgisSdkPrError:
        return None


def push(head: str) -> None:
    """Publish the branch, so the pull request has a head to point at."""
    run_git(["push", "--set-upstream", "origin", head])


def create(request: PullRequestRequest) -> str:
    """Create the pull request and hand back the URL GitHub answered."""
    branch = request.branch
    arguments = [
        "pr",
        "create",
        "--base",
        branch.base,
        "--head",
        branch.head,
        "--title",
        request.title,
        "--body",
        request.body,
    ]
    if request.draft:
        arguments.append("--draft")
    if request.repo:
        arguments.extend(["--repo", request.repo])
    return run_gh(arguments).strip()


def open_pr(request: PullRequestRequest) -> int:
    """Push the branch and open its pull request, or say why not."""
    if request.branch.head == request.branch.base:
        print(
            "pr open: the base branch is the default branch; "
            "push the work to its own branch first",
            flush=True,
        )
        return 1
    number = existing(request.repo)
    if number is not None:
        print(
            f"pr open: #{number} is already open - "
            f"watch it with `python -m automation.pr --pr {number}`",
            flush=True,
        )
        return 1
    push(request.branch.head)
    print(create(request), flush=True)
    return 0


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
    if not snapshot.checks:
        # A pull request opened seconds ago has no check-runs yet, and an empty
        # rollup is not a green one: without this the watcher answered "all
        # checks green" before the first workflow had even been queued.
        print(f"pr #{number}: no checks reported yet", flush=True)
        return None, 0
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


def _body(args: argparse.Namespace, items: tuple[str, ...]) -> str:
    """A written body wins, then a body file, then the commits themselves."""
    if args.body:
        return args.body
    if args.body_file:
        return Path(args.body_file).read_text(encoding="utf-8")
    return body_for(items)


def _request(args: argparse.Namespace) -> PullRequestRequest:
    """Read the checkout and the flags into one request."""
    head = current_branch()
    base = args.base or default_branch(args.repo)
    items = () if head == base else subjects(base)
    return PullRequestRequest(
        branch=Branch(head=head, base=base),
        title=args.title or title_for(items),
        body=_body(args, items),
        draft=args.draft,
        repo=args.repo,
    )


def _watch_flags(parser: argparse.ArgumentParser) -> None:
    """The polling knobs `watch` reads from the parsed namespace."""
    parser.add_argument("--pr", type=int, default=0, help="number; 0 is the branch's")
    parser.add_argument(
        "--interval", type=int, default=15, help="seconds between polls"
    )
    parser.add_argument("--timeout", type=int, default=0, help="0 waits forever")


def _open_flags(parser: argparse.ArgumentParser) -> None:
    """What `open` needs beyond the checkout."""
    parser.add_argument("--title", default="", help="defaults to the newest commit")
    parser.add_argument("--body", default="", help="the body, inline")
    parser.add_argument("--body-file", default="", help="read the body from a file")
    parser.add_argument("--base", default="", help="the branch to merge into")
    parser.add_argument("--draft", action="store_true", help="open as a draft")


def _parser() -> argparse.ArgumentParser:
    """One action, then the flags each action reads from the same namespace."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        nargs="?",
        default="watch",
        choices=("open", "watch"),
        help="open a pull request, or watch one; default: watch",
    )
    parser.add_argument("--repo", default="", help="owner/name; defaults to here")
    _watch_flags(parser)
    _open_flags(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.action == "watch":
        return watch(
            pr=args.pr, interval=args.interval, timeout=args.timeout, repo=args.repo
        )
    try:
        return open_pr(_request(args))
    except QgisSdkPrError as exc:
        print(f"pr open: {exc}", flush=True)
        return 127


if __name__ == "__main__":
    sys.exit(main())
