"""Watch a pull request's CI: poll every 15 seconds, break on the first error.

`gh pr checks --watch` waits for every check to finish before it answers, so a
job that fails in the first minute still costs the whole run. The watcher here
answers as soon as any check fails, while the rest are still queued or running.
"""

from __future__ import annotations

import json

import pytest

from automation import pr


def _check(name: str, status: str, conclusion: str | None) -> pr.Check:
    return pr.Check(name=name, status=status, conclusion=conclusion)


def _snapshot(*checks: pr.Check, state: str = "OPEN") -> pr.Snapshot:
    return pr.Snapshot(pr=211, state=state, checks=tuple(checks))


def _green() -> pr.Snapshot:
    return _snapshot(
        _check("Linux checks", "COMPLETED", "SUCCESS"),
        _check("QGIS 3.44 LTS", "COMPLETED", "SUCCESS"),
    )


def _pending() -> pr.Snapshot:
    return _snapshot(
        _check("Linux checks", "IN_PROGRESS", None),
        _check("QGIS 3.44 LTS", "QUEUED", None),
    )


def _failed() -> pr.Snapshot:
    return _snapshot(
        _check("Linux checks", "COMPLETED", "FAILURE"),
        _check("QGIS 3.44 LTS", "IN_PROGRESS", None),
    )


def test_all_green_exits_zero_without_sleeping(monkeypatch) -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def fetch(number: int, repo: str = "") -> pr.Snapshot:
        calls.append(number)
        return _green()

    monkeypatch.setattr(pr, "fetch", fetch)
    monkeypatch.setattr(pr, "sleep", sleeps.append)
    assert pr.watch(pr=211) == 0
    assert calls == [211]
    assert sleeps == []


def test_first_failure_breaks_without_waiting_for_pending(monkeypatch, capsys) -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def fetch(number: int, repo: str = "") -> pr.Snapshot:
        calls.append(number)
        return _failed()

    monkeypatch.setattr(pr, "fetch", fetch)
    monkeypatch.setattr(pr, "sleep", sleeps.append)
    assert pr.watch(pr=211) == 1
    # One poll, no sleep: the pending check is not waited for.
    assert calls == [211]
    assert sleeps == []
    assert "Linux checks" in capsys.readouterr().out


def test_pending_then_green_polls_until_done(monkeypatch) -> None:
    snapshots = iter([_pending(), _green()])
    sleeps: list[float] = []

    monkeypatch.setattr(pr, "fetch", lambda number, repo="": next(snapshots))
    monkeypatch.setattr(pr, "sleep", sleeps.append)
    assert pr.watch(pr=211, interval=15) == 0
    assert sleeps == [15]


def test_timeout_returns_two(monkeypatch) -> None:
    clock = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(pr, "fetch", lambda number, repo="": _pending())
    monkeypatch.setattr(pr, "sleep", sleep)
    monkeypatch.setattr(pr, "monotonic", lambda: clock[0])
    assert pr.watch(pr=211, interval=15, timeout=30) == 2
    assert sleeps == [15, 15]


@pytest.mark.parametrize("conclusion", sorted(pr.FAILED_CONCLUSIONS))
def test_failed_conclusions_break(monkeypatch, conclusion: str) -> None:
    snapshot = _snapshot(
        _check("Linux checks", "COMPLETED", conclusion),
        _check("QGIS 3.44 LTS", "QUEUED", None),
    )
    monkeypatch.setattr(pr, "fetch", lambda number, repo="": snapshot)
    monkeypatch.setattr(pr, "sleep", lambda seconds: None)
    assert pr.watch(pr=211) == 1


@pytest.mark.parametrize("conclusion", sorted(pr.PASSED_CONCLUSIONS))
def test_passed_conclusions_do_not_break(monkeypatch, conclusion: str) -> None:
    snapshot = _snapshot(_check("Linux checks", "COMPLETED", conclusion))
    monkeypatch.setattr(pr, "fetch", lambda number, repo="": snapshot)
    monkeypatch.setattr(pr, "sleep", lambda seconds: None)
    assert pr.watch(pr=211) == 0


def test_resolves_pr_from_current_branch_when_pr_is_zero(monkeypatch) -> None:
    seen: list[int] = []

    def fetch(number: int, repo: str = "") -> pr.Snapshot:
        seen.append(number)
        return _green()

    monkeypatch.setattr(pr, "resolve_pr", lambda repo="": 211)
    monkeypatch.setattr(pr, "fetch", fetch)
    monkeypatch.setattr(pr, "sleep", lambda seconds: None)
    assert pr.watch() == 0
    assert seen == [211]


def test_gh_errors_give_up_after_three(monkeypatch) -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def fetch(number: int, repo: str = "") -> pr.Snapshot:
        calls.append(number)
        raise pr.QgisSdkPrError("gh failed")

    monkeypatch.setattr(pr, "fetch", fetch)
    monkeypatch.setattr(pr, "sleep", sleeps.append)
    assert pr.watch(pr=211, interval=15) == 127
    assert calls == [211, 211, 211]
    assert sleeps == [15, 15]


def test_main_parses_args(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def watch(pr: int = 0, interval: int = 15, timeout: int = 0, repo: str = "") -> int:
        seen.update(pr=pr, interval=interval, timeout=timeout, repo=repo)
        return 1

    monkeypatch.setattr(pr, "watch", watch)
    assert pr.main(["--pr", "211", "--interval", "15", "--timeout", "60"]) == 1
    assert seen == {"pr": 211, "interval": 15, "timeout": 60, "repo": ""}


def test_fetch_parses_status_check_rollup(monkeypatch) -> None:
    payload = json.dumps(
        {
            "state": "OPEN",
            "statusCheckRollup": [
                {
                    "name": "Linux checks",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                },
                {"name": "QGIS 3.44 LTS", "status": "IN_PROGRESS", "conclusion": None},
            ],
        }
    )
    monkeypatch.setattr(pr, "run_gh", lambda arguments: payload)
    snapshot = pr.fetch(211)
    assert snapshot.pr == 211
    assert snapshot.state == "OPEN"
    assert [check.name for check in snapshot.failed] == []
    assert [check.name for check in snapshot.pending] == ["QGIS 3.44 LTS"]
    assert [check.name for check in snapshot.passed] == ["Linux checks"]


def test_resolve_pr_parses_number(monkeypatch) -> None:
    monkeypatch.setattr(pr, "run_gh", lambda arguments: '{"number": 211}')
    assert pr.resolve_pr() == 211


def _recording_git(
    seen: list[list[str]], log: str = "feat(x): one\nfix(y): two\n"
) -> object:
    """A ``git`` that records its calls and answers the commit log."""

    def run_git(arguments: list[str]) -> str:
        seen.append(arguments)
        if arguments[0] == "log":
            return log
        if arguments[0] == "rev-parse":
            return "feature-branch\n"
        return ""

    return run_git


def _recording_gh(seen: list[list[str]], existing: int | None = None) -> object:
    """A ``gh`` that records its calls and answers ``pr view`` only if asked."""

    def run_gh(arguments: list[str]) -> str:
        seen.append(arguments)
        if arguments[:2] == ["repo", "view"]:
            return "main\n"
        if arguments[0] == "pr" and "view" in arguments:
            if existing is None:
                raise pr.QgisSdkPrError("no pull request for the current branch")
            return json.dumps({"number": existing})
        return "https://github.com/Archont561/qgis-sdk/pull/215\n"

    return run_gh


def _request(**overrides: object) -> pr.PullRequestRequest:
    values: dict[str, object] = {
        "branch": pr.Branch(head="feature-branch", base="main"),
        "title": "feat(x): one",
        "body": "- feat(x): one",
    }
    values.update(overrides)
    return pr.PullRequestRequest(**values)  # type: ignore[arg-type]


def test_open_pushes_the_branch_then_creates_the_pull_request(
    monkeypatch, capsys
) -> None:
    """One command replaces the hand-written push-then-`gh api` sequence."""
    git_calls: list[list[str]] = []
    gh_calls: list[list[str]] = []
    monkeypatch.setattr(pr, "run_git", _recording_git(git_calls))
    monkeypatch.setattr(pr, "run_gh", _recording_gh(gh_calls))
    assert pr.open_pr(_request()) == 0
    assert git_calls == [["push", "--set-upstream", "origin", "feature-branch"]]
    created = gh_calls[-1]
    assert created[:2] == ["pr", "create"]
    assert created[created.index("--base") + 1] == "main"
    assert created[created.index("--head") + 1] == "feature-branch"
    assert created[created.index("--title") + 1] == "feat(x): one"
    assert "pull/215" in capsys.readouterr().out


def test_open_refuses_a_branch_that_already_has_a_pull_request(
    monkeypatch, capsys
) -> None:
    """A second PR for one branch is a mistake, so the existing one is named."""
    git_calls: list[list[str]] = []
    gh_calls: list[list[str]] = []
    monkeypatch.setattr(pr, "run_git", _recording_git(git_calls))
    monkeypatch.setattr(pr, "run_gh", _recording_gh(gh_calls, existing=214))
    assert pr.open_pr(_request()) == 1
    assert git_calls == []
    assert [call[:2] for call in gh_calls] == [["pr", "view"]]
    assert "#214" in capsys.readouterr().out


def test_open_refuses_to_open_the_default_branch_against_itself(
    monkeypatch, capsys
) -> None:
    """`main` is not a pull request; nothing is pushed and nothing is created."""
    git_calls: list[list[str]] = []
    gh_calls: list[list[str]] = []
    monkeypatch.setattr(pr, "run_git", _recording_git(git_calls))
    monkeypatch.setattr(pr, "run_gh", _recording_gh(gh_calls))
    request = _request(branch=pr.Branch(head="main", base="main"))
    assert pr.open_pr(request) == 1
    assert git_calls == [] and gh_calls == []
    assert "base branch" in capsys.readouterr().out


def test_main_reads_the_branch_commits_into_title_and_body(monkeypatch) -> None:
    """The defaults come from the commits, so no title has to be invented."""
    seen: list[pr.PullRequestRequest] = []
    git_calls: list[list[str]] = []
    monkeypatch.setattr(
        pr, "run_git", _recording_git(git_calls, "fix(a): one\nfeat(b): two\n")
    )
    monkeypatch.setattr(pr, "run_gh", _recording_gh([], existing=215))
    monkeypatch.setattr(pr, "open_pr", lambda request: seen.append(request) or 0)
    assert pr.main(["open"]) == 0
    request = seen[0]
    assert request.branch == pr.Branch(head="feature-branch", base="main")
    assert request.title == "feat(b): two"
    assert request.body == "- fix(a): one\n- feat(b): two"


def test_main_prefers_an_explicit_title_body_and_base(monkeypatch, tmp_path) -> None:
    """A written title, a body file and a base override all win."""
    seen: list[pr.PullRequestRequest] = []
    monkeypatch.setattr(pr, "run_git", _recording_git([]))
    monkeypatch.setattr(pr, "run_gh", _recording_gh([]))
    monkeypatch.setattr(pr, "open_pr", lambda request: seen.append(request) or 0)
    body = tmp_path / "body.md"
    body.write_text("## Change\n\nOne thing.\n", encoding="utf-8")
    argv = ["open", "--title", "refactor(x): it", "--body-file", str(body)]
    assert pr.main([*argv, "--base", "release"]) == 0
    assert seen[0].title == "refactor(x): it"
    assert seen[0].body == "## Change\n\nOne thing.\n"
    assert seen[0].branch.base == "release"


def test_main_reports_a_gh_failure_as_127(monkeypatch, capsys) -> None:
    """A refused `gh pr create` is an environment problem, not a bad request."""

    def run_gh(arguments: list[str]) -> str:
        raise pr.QgisSdkPrError("gh pr create failed: not authenticated")

    monkeypatch.setattr(pr, "run_git", _recording_git([]))
    monkeypatch.setattr(pr, "run_gh", run_gh)
    assert pr.main(["open"]) == 127
    assert "not authenticated" in capsys.readouterr().out
