"""The clean-code pin and its curated rule set are a contract, not a default.

`rude-clean-code` 0.3.1 ships 59 rules. The gate deliberately measures only the
deterministic structural WARNING rules in CC0-CC3; a future version bump must
not silently widen the budget by enabling heuristics, architecture or doc
hygiene families. These guards read the three files that make that decision.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

STRUCTURAL_INFO = frozenset(
    {
        "CC002",
        "CC105",
        "CC106",
        "CC108",
        "CC204",
        "CC205",
        "CC206",
        "CC304",
        "CC305",
        "CC307",
    }
)
EXCLUDED_FAMILIES = frozenset({"CC4", "CC5", "CC6", "CC7", "CC8", "CC9"})


def test_the_pypi_pin_and_lock_agree_on_the_newest_release() -> None:
    manifest = tomllib.loads((ROOT / "pixi.toml").read_text(encoding="utf-8"))
    pin = manifest["feature"]["python"]["pypi-dependencies"]["rude-clean-code"]
    assert pin == "==0.3.1"

    lock = (ROOT / "pixi.lock").read_text(encoding="utf-8")
    assert "rude_clean_code-0.3.1-py3-none-any.whl" in lock
    assert "rude_clean_code-0.1.0-py3-none-any.whl" not in lock
    assert "name: rude-clean-code\n  version: 0.3.1" in lock


def test_only_deterministic_structural_rules_are_selected() -> None:
    rude = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "rude"
    ]
    assert rude["select"] == ["CC0", "CC1", "CC2", "CC3"]
    ignored = set(rude["ignore"])
    assert STRUCTURAL_INFO <= ignored
    assert EXCLUDED_FAMILIES <= ignored

    rules = rude["rules"]
    assert rules["CC001"]["max_lines"] == 400
    assert rules["CC004"]["max_relative_depth"] == 2
    assert rules["CC207"]["max_bases"] == 3
    assert rules["CC311"]["max_lines"] == 20
    # The nine thresholds that built the original budget are unchanged.
    assert rules["CC101"]["max_lines"] == 30
    assert rules["CC102"]["max_parameters"] == 5
    assert rules["CC104"]["max_locals"] == 10
    assert rules["CC202"]["max_methods"] == 15
    assert rules["CC303"]["max_branches"] == 10
