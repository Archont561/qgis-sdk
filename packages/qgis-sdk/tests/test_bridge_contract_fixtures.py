"""The checked-in bridge cases are produced by the dispatcher, never by hand.

The file is consumed by the TypeScript client tests, so it has to mean the same
thing on both sides. Python therefore rebuilds it here and refuses to drift: a
changed refusal code or a changed reply shape fails this test until the fixture
is regenerated, and the regeneration runs the real dispatcher rather than
editing JSON.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = PROJECT_ROOT / "scripts" / "generate_bridge_cases.py"
CASES_PATH = (
    PROJECT_ROOT.parent
    / "qgis-sdk-bridge"
    / "tests"
    / "contracts"
    / "bridge"
    / "cases.json"
)


def _generator():
    spec = importlib.util.spec_from_file_location("bridge_cases_generator", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _checked_in() -> dict:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def test_the_checked_in_cases_match_the_dispatcher() -> None:
    expected = _generator().build_cases()

    assert _checked_in() == json.loads(json.dumps(expected)), (
        "regenerate with: python packages/qgis-sdk/scripts/generate_bridge_cases.py"
    )


def test_every_case_names_a_unique_refusal_or_value() -> None:
    cases = _checked_in()["cases"]

    names = [case["name"] for case in cases]
    assert len(names) == len(set(names))
    assert set(names) == {
        "success",
        "unknown-operation",
        "not-authorized",
        "stale-generation",
        "invalid-protocol",
        "invalid-payload",
        "not-serializable",
        "operation-failed",
        "cancelled",
    }


def test_every_reply_carries_the_protocol_and_survives_json() -> None:
    payload = _checked_in()

    assert payload["protocol"] == 1
    for case in payload["cases"]:
        assert case["reply"]["protocol"] == payload["protocol"]
        assert json.loads(json.dumps(case["reply"])) == case["reply"]


def test_every_expectation_describes_its_own_reply() -> None:
    for case in _checked_in()["cases"]:
        reply = case["reply"]
        expect = case["expect"]

        assert reply["ok"] is expect["ok"]
        if expect["ok"]:
            assert expect["value"] == reply["value"]
        else:
            assert expect["code"] == reply["error"]["code"]
