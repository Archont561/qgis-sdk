"""Tests for the headless Qt scheduler qualification harness.

The summary and verdict helpers are QGIS-free and deterministic, so they run in the
normal suite. The end-to-end run is opt-in because it needs a real QGIS
installation, and it is explicitly not a Desktop GUI qualification: the harness has
no display, no real ``iface``, and drives Qt with ``processEvents()``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from qt_scheduler_smoke import (
    DECIDING_CRITERIA,
    VERDICT_ADOPT,
    VERDICT_REVIEW,
    GapSummary,
    SchedulerReport,
    _Heartbeat,
    decide_verdict,
    delivered_only_on,
    ran_on_a_different_thread,
    summarise_gaps,
)

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
SMOKE_SCRIPT = SCRIPTS_DIR / "qt_scheduler_smoke.py"
SMOKE_ENV_FLAG = "QGIS_SDK_QT_SCHEDULER"


def test_a_phase_measures_only_the_heartbeats_after_its_own_baseline() -> None:
    """The sampler is shared by every phase, so a phase must not read another's gaps."""
    heartbeat = _Heartbeat([1.0, 1.01, 1.025, 1.03])

    assert heartbeat.baseline_index() == 3
    assert heartbeat.gaps_since(1) == pytest.approx([15.0, 5.0])
    assert heartbeat.has_at_least(3)
    assert not heartbeat.has_at_least(5)
    summary = heartbeat.phase(1)
    assert summary.count == 2
    assert summary.max_ms == pytest.approx(15.0)
    assert summary.mean_ms == pytest.approx(10.0)


def test_an_unstarted_heartbeat_yields_no_gaps_rather_than_a_negative_index() -> None:
    """A port that samples before the first beat must summarise zero, not crash."""
    heartbeat = _Heartbeat([])

    assert heartbeat.baseline_index() == 0
    assert heartbeat.gaps_since(0) == []
    assert heartbeat.phase(0).count == 0


def all_criteria() -> dict[str, bool]:
    return dict.fromkeys(DECIDING_CRITERIA, True)


def make_report(**overrides: object) -> SchedulerReport:
    base: dict[str, object] = {
        "platform": "Linux-6.1.0-x86_64",
        "python_version": "3.14.8",
        "qgis_version": "4.2.3-Belem do Para",
        "qt_version": "6.11.2",
        "qgis_initialised": True,
        "event_loop_polled": True,
        "gui_thread_id": 1,
        "worker_thread_ids": (2,),
        "delivery_thread_ids": (1,),
        "blocking_phase": GapSummary(count=3, max_ms=61.0, mean_ms=30.5),
        "scheduled_phase": GapSummary(count=40, max_ms=3.0, mean_ms=2.0),
        "gui_responsive_for_scheduled_work": True,
        "handoff_delivered_on_gui_thread": True,
        "work_ran_off_the_gui_thread": True,
        "worker_acknowledged_cancellation": True,
        "author_cleanup_ran": True,
        "late_report_dropped_after_disposal": True,
        "replacement_refused_while_stuck": True,
        "refused_blocker": "job 4 is waiting on an unresolved worker handoff",
        "verdict": VERDICT_ADOPT,
        "scope_review_criteria": (),
    }
    return SchedulerReport(**{**base, **overrides})  # type: ignore[arg-type]


def test_gaps_are_summarised_from_the_measured_order() -> None:
    assert summarise_gaps([]) == GapSummary(count=0, max_ms=0.0, mean_ms=0.0)

    summary = summarise_gaps([5.0, 15.0, 25.0])

    assert summary.count == 3
    assert summary.max_ms == 25.0
    assert summary.mean_ms == 15.0


def test_a_phase_is_responsive_only_when_no_gap_exceeds_the_budget() -> None:
    tight = summarise_gaps([2.0, 3.0, 2.5])
    stalled = summarise_gaps([2.0, 60.0])

    assert tight.responsive(budget_ms=40) is True
    assert tight.stalled(budget_ms=40) is False
    assert stalled.responsive(budget_ms=40) is False
    assert stalled.stalled(budget_ms=40) is True
    assert summarise_gaps([]).responsive(budget_ms=40) is False


def test_deliveries_must_all_land_on_the_thread_that_drives_the_scheduler() -> None:
    assert delivered_only_on(7, [7, 7]) is True
    assert delivered_only_on(7, [7, 8]) is False
    assert delivered_only_on(7, []) is False

    assert ran_on_a_different_thread(7, [8, 9]) is True
    assert ran_on_a_different_thread(7, [8, 7]) is False
    assert ran_on_a_different_thread(7, []) is False


def test_a_failing_criterion_forces_scope_review_instead_of_a_downgrade() -> None:
    verdict, reasons = decide_verdict(all_criteria())
    assert verdict == VERDICT_ADOPT
    assert reasons == ()

    for criterion in DECIDING_CRITERIA:
        failing = all_criteria() | {criterion: False}

        verdict, reasons = decide_verdict(failing)

        assert verdict == VERDICT_REVIEW
        assert reasons == (criterion,)


def test_the_verdict_ignores_criteria_that_cannot_change_the_outcome() -> None:
    verdict, reasons = decide_verdict({"event_loop_polled": False})

    assert verdict == VERDICT_REVIEW
    assert reasons == DECIDING_CRITERIA


def test_a_report_passes_only_with_an_adopt_verdict_and_a_polled_loop() -> None:
    assert make_report().passed is True
    assert make_report(event_loop_polled=False).passed is False
    assert make_report(author_cleanup_ran=False).passed is False
    assert (
        make_report(
            verdict=VERDICT_REVIEW,
            scope_review_criteria=("work_ran_off_the_gui_thread",),
        ).passed
        is False
    )
    assert make_report(qgis_initialised=False).passed is False


def test_criteria_expose_exactly_the_measured_deciding_signals() -> None:
    assert set(make_report().criteria) == set(DECIDING_CRITERIA)


def test_report_serialises_to_a_stable_json_shape() -> None:
    payload = json.loads(json.dumps(make_report().to_dict(), sort_keys=True))

    assert payload["passed"] is True
    assert payload["scheduled_phase_max_ms"] == 3.0
    assert payload["blocking_phase_max_ms"] == 61.0
    assert payload["worker_thread_ids"] == [2]
    assert payload["scope_review_criteria"] == []
    assert set(payload) == {
        "author_cleanup_ran",
        "blocking_phase",
        "blocking_phase_max_ms",
        "delivery_thread_ids",
        "error",
        "event_loop_polled",
        "gui_responsive_for_scheduled_work",
        "gui_thread_id",
        "handoff_delivered_on_gui_thread",
        "late_report_dropped_after_disposal",
        "passed",
        "platform",
        "python_version",
        "qt_version",
        "qgis_initialised",
        "qgis_version",
        "refused_blocker",
        "replacement_refused_while_stuck",
        "scheduled_phase",
        "scheduled_phase_max_ms",
        "scope_review_criteria",
        "verdict",
        "worker_acknowledged_cancellation",
        "worker_thread_ids",
        "work_ran_off_the_gui_thread",
    }


@pytest.mark.desktop
@pytest.mark.skipif(
    os.environ.get(SMOKE_ENV_FLAG) != "1",
    reason=f"set {SMOKE_ENV_FLAG}=1 to run the real headless Qt scheduler smoke",
)
def test_headless_qt_scheduler_smoke_adopts_the_seam() -> None:
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT)],
        cwd=SCRIPTS_DIR.parents[1],
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["verdict"] == VERDICT_ADOPT
    assert payload["scope_review_criteria"] == []
    assert payload["qgis_initialised"] is True
    assert payload["event_loop_polled"] is True
    assert payload["gui_responsive_for_scheduled_work"] is True
    assert payload["handoff_delivered_on_gui_thread"] is True
    assert payload["work_ran_off_the_gui_thread"] is True
    assert payload["worker_acknowledged_cancellation"] is True
    assert payload["late_report_dropped_after_disposal"] is True
    assert payload["replacement_refused_while_stuck"] is True
    assert payload["refused_blocker"] is not None
    assert payload["blocking_phase_max_ms"] > payload["scheduled_phase_max_ms"]
