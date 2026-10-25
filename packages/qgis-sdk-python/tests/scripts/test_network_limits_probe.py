"""Tests for the network limits measurement harness (TASK-5, doc-15).

The recommendation rule is QGIS-free and deterministic, so it runs in the normal
suite with hand-written findings; the measurement itself needs a real QGIS and
is opt-in through ``QGIS_SDK_NETWORK_PROBE=1``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from network_limits_probe import (
    BROWSER_REDIRECT_LIMIT,
    GUI_STALL_BUDGET_MS,
    BodyFinding,
    ProbeReport,
    RedirectFindings,
    recommend,
)
from qgis_sdk.models import DEFAULT_MAX_BODY_BYTES, DEFAULT_MAX_REDIRECTS

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
PROBE_SCRIPT = SCRIPTS_DIR / "network_limits_probe.py"
PROBE_ENV_FLAG = "QGIS_SDK_NETWORK_PROBE"


def body(size_mib: int, finish_stall_ms: float) -> BodyFinding:
    return BodyFinding(
        size_mib=size_mib,
        finish_stall_ms=finish_stall_ms,
        worst_stall_ms=finish_stall_ms + 1.0,
        transfer_ms=size_mib * 2.0,
        resident_delta_mib=size_mib * 1.5,
    )


def redirects(**overrides: object) -> RedirectFindings:
    base: dict[str, object] = {
        "policy": "NoLessSafeRedirectPolicy",
        "unaided_hops_followed": 50,
        "headers_forwarded_cross_origin": ("Authorization", "Cookie"),
        "manual_hop_mean_ms": 0.7,
    }
    base.update(overrides)
    return RedirectFindings(**base)  # type: ignore[arg-type]


MEASURED = (
    body(1, 0.3),
    body(4, 1.4),
    body(8, 2.8),
    body(16, 13.7),
    body(32, 42.0),
    body(64, 79.0),
)


def test_the_body_ceiling_is_the_largest_size_inside_the_stall_budget() -> None:
    outcome = recommend(redirects(), MEASURED)

    assert outcome.max_body_mib == 16
    assert outcome.max_body_mib * 1024 * 1024 == DEFAULT_MAX_BODY_BYTES
    assert any("16 MiB" in reason for reason in outcome.reasons)


def test_a_size_exactly_on_the_budget_counts_as_inside_it() -> None:
    """The 32 MiB result straddled the budget across runs; the rule is the tie-break."""
    outcome = recommend(redirects(), (*MEASURED[:4], body(32, GUI_STALL_BUDGET_MS)))

    assert outcome.max_body_mib == 32


def test_no_body_inside_the_budget_falls_back_to_the_smallest_measured() -> None:
    outcome = recommend(redirects(), (body(8, 50.0), body(16, 90.0)))

    assert outcome.max_body_mib == 8
    assert "no measured body stayed inside the stall budget" in outcome.reasons


def test_a_cheap_hop_keeps_the_browser_redirect_limit() -> None:
    outcome = recommend(redirects(manual_hop_mean_ms=0.7), MEASURED)

    assert outcome.max_redirects == BROWSER_REDIRECT_LIMIT == DEFAULT_MAX_REDIRECTS


def test_an_expensive_hop_shrinks_the_redirect_limit_to_the_budget() -> None:
    outcome = recommend(redirects(manual_hop_mean_ms=5.0), MEASURED)

    assert outcome.max_redirects == 8
    assert any("allows 8 hops" in reason for reason in outcome.reasons)


def test_forwarded_credentials_make_the_transport_follow_redirects_itself() -> None:
    forwarding = recommend(redirects(), MEASURED)
    dropping = recommend(redirects(headers_forwarded_cross_origin=()), MEASURED)

    assert forwarding.transport_follows_redirects_itself
    assert any("Authorization, Cookie" in reason for reason in forwarding.reasons)
    assert not dropping.transport_follows_redirects_itself


def test_a_report_serialises_to_plain_json() -> None:
    report = ProbeReport(
        platform="Linux",
        python_version="3.14.8",
        qgis_version="4.2.3",
        qt_version="6.11.2",
        redirects=redirects(),
        bodies=MEASURED[:2],
        recommended=recommend(redirects(), MEASURED[:2]),
    )

    payload = json.loads(json.dumps(report.as_dict()))

    assert payload["recommended"]["max_body_mib"] == 4
    assert payload["redirects"]["headers_forwarded_cross_origin"] == [
        "Authorization",
        "Cookie",
    ]
    assert payload["error"] is None


@pytest.mark.skipif(
    os.environ.get(PROBE_ENV_FLAG) != "1",
    reason=f"set {PROBE_ENV_FLAG}=1 with QGIS in the active prefix to run the measurement",
)
def test_the_probe_measures_a_real_qgis_and_agrees_with_the_shipped_defaults() -> None:
    completed = subprocess.run(
        [sys.executable, str(PROBE_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    report = json.loads(completed.stdout[completed.stdout.index("{") :])
    assert report["error"] is None
    assert report["redirects"]["unaided_hops_followed"] >= 10
    assert report["recommended"]["max_redirects"] == DEFAULT_MAX_REDIRECTS
    # 32 MiB sits on the budget edge (doc-15); the shipped ceiling is the safe side.
    assert report["recommended"]["max_body_mib"] >= DEFAULT_MAX_BODY_BYTES // (
        1024 * 1024
    )
