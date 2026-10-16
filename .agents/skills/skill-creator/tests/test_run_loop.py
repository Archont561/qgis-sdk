from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts import run_loop as run_loop_script


def test_loop_keeps_legacy_result_shape_and_selects_the_best_train_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_path = tmp_path / "demo"
    skill_path.mkdir()
    (skill_path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Use this skill for demos.\n---\n\nBody.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(run_loop_script, "find_project_root", lambda: tmp_path)

    def successful_eval(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["eval_set"] == [{"query": "demo", "should_trigger": True}]
        result = {
            "query": "demo",
            "should_trigger": True,
            "trigger_rate": 1.0,
            "triggers": 1,
            "runs": 1,
            "pass": True,
        }
        return {
            "results": [result],
            "summary": {"total": 1, "passed": 1, "failed": 0},
        }

    monkeypatch.setattr(run_loop_script, "run_eval", successful_eval)

    output = run_loop_script.run_loop(
        eval_set=[{"query": "demo", "should_trigger": True}],
        skill_path=skill_path,
        description_override=None,
        num_workers=1,
        timeout=1,
        max_iterations=1,
        runs_per_query=1,
        trigger_threshold=0.5,
        holdout=0,
        model="test-model",
        verbose=False,
    )

    assert output["exit_reason"] == "all_passed (iteration 1)"
    assert output["best_score"] == "1/1"
    assert output["best_train_score"] == "1/1"
    assert output["best_test_score"] is None
    assert output["history"][0]["results"] == output["history"][0]["train_results"]
