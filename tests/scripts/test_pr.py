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
