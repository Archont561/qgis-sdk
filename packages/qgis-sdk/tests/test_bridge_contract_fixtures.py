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

from bridge_steps import ContractHost

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
    generator = _generator()
    expected = generator.build_cases()

    assert _checked_in() == json.loads(json.dumps(expected)), (
        "regenerate with: python packages/qgis-sdk/scripts/generate_bridge_cases.py"
    )
    # Byte for byte too: the file is formatted the way biome formats it, so the
    # generator and the formatter never take turns rewriting it.
    assert CASES_PATH.read_text(encoding="utf-8") == generator.render(expected)


def test_the_rendering_keeps_short_scalar_arrays_on_one_line() -> None:
    """The collapse is deliberately narrow - an array of scalars that fits in
    80 columns - so the generator agrees with biome on the shapes the cases
    contain and leaves every other array and object broken as ``json.dumps``
    wrote it."""
    render = _generator().render

    text = render(
        {
            "short": ["read", "write"],
            "nested": [[1], [2]],
            "long": [f"item-{index:02d}" for index in range(12)],
            "object": [{"k": 1}],
        }
    )

    assert '\t"short": ["read", "write"]\n' in text
    assert '\t"nested": [\n\t\t[1],\n\t\t[2]\n\t]' in text
    assert '\t"long": [\n\t\t"item-00",' in text
    assert '\t"object": [\n\t\t{\n\t\t\t"k": 1\n\t\t}\n\t]' in text


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
        "invalid-result",
        "cancelled",
        "forged-identity",
        "expired-handle",
        "release-borrowed",
    }


def _case(name: str) -> dict:
    return next(case for case in _checked_in()["cases"] if case["name"] == name)


def test_every_checked_in_case_replays_against_a_live_host(
    contract_host: ContractHost, bridge_cases: dict[str, dict]
) -> None:
    """The ordinary-test side of what ``bridge_contract.feature`` reads aloud:
    the same fixture, the same ``send``, every case at once."""
    for name, case in bridge_cases.items():
        host = contract_host.fresh().prepare(name)

        reply = host.send(case["request"])

        assert host.expectation(reply) == case["expect"], name


def test_a_forged_identity_in_the_request_is_ignored_not_honoured() -> None:
    """The host-minted binding answers, whatever the envelope and payload claim."""
    case = _case("forged-identity")

    assert case["request"]["view_id"] == "view-2"
    assert case["request"]["payload"]["view_id"] == "view-2"
    assert case["expect"] == {
        "ok": True,
        "value": {"view_id": "view-1", "generation": 0},
    }


def test_an_expired_file_ref_is_refused_as_stale_without_the_path() -> None:
    case = _case("expired-handle")

    assert case["expect"] == {"ok": False, "code": "stale_handle"}
    assert "expired" in case["reply"]["error"]["message"]
    assert "/" not in case["reply"]["error"]["message"]


def test_releasing_a_borrowed_handle_retains_it_and_reports_each_outcome() -> None:
    case = _case("release-borrowed")

    assert case["request"]["kind"] == "release"
    assert case["expect"]["ok"] is True
    outcomes = {
        item["id"]: item["outcome"] for item in case["expect"]["value"]["released"]
    }
    assert outcomes == {
        "layer-1": "borrowed_retained",
        "layer-9": "already_released",
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
