from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import improve_description as improve_script


def _eval_results() -> dict:
    return {
        "summary": {"passed": 1, "failed": 1, "total": 2},
        "results": [
            {
                "query": "open a raster",
                "should_trigger": True,
                "pass": False,
                "triggers": 0,
                "runs": 3,
            },
            {
                "query": "write a poem",
                "should_trigger": False,
                "pass": False,
                "triggers": 2,
                "runs": 3,
            },
        ],
    }


def test_improvement_uses_failure_context_and_persists_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts: list[str] = []

    def respond(prompt: str, model: str | None, timeout: int = 300) -> str:
        assert model == "test-model"
        prompts.append(prompt)
        return "<new_description>Use this skill for raster tasks.</new_description>"

    monkeypatch.setattr(improve_script, "_call_claude", respond)
    log_dir = tmp_path / "logs"

    result = improve_script.improve_description(
        skill_name="raster-tools",
        skill_content="The skill processes rasters.",
        current_description="Old description.",
        eval_results=_eval_results(),
        history=[],
        model="test-model",
        test_results={"summary": {"passed": 1, "total": 2}},
        log_dir=log_dir,
        iteration=2,
    )

    assert result == "Use this skill for raster tasks."
    assert "FAILED TO TRIGGER" in prompts[0]
    assert "FALSE TRIGGERS" in prompts[0]
    assert "Train: 1/2, Test: 1/2" in prompts[0]
    transcript = json.loads((log_dir / "improve_iter_2.json").read_text())
    assert transcript["final_description"] == result
    assert transcript["over_limit"] is False


def test_overlong_model_response_gets_one_shortening_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = iter(
        [
            f"<new_description>{'x' * 1025}</new_description>",
            "<new_description>Short description.</new_description>",
        ]
    )
    prompts: list[str] = []

    def respond(prompt: str, model: str | None, timeout: int = 300) -> str:
        prompts.append(prompt)
        return next(responses)

    monkeypatch.setattr(improve_script, "_call_claude", respond)
    log_dir = tmp_path / "logs"

    result = improve_script.improve_description(
        skill_name="demo",
        skill_content="Content.",
        current_description="Old.",
        eval_results={"summary": {"passed": 1, "total": 1}, "results": []},
        history=[],
        model="test-model",
        log_dir=log_dir,
        iteration=1,
    )

    assert result == "Short description."
    assert len(prompts) == 2
    assert "over the 1024-character hard limit" in prompts[1]
    transcript = json.loads((log_dir / "improve_iter_1.json").read_text())
    assert transcript["rewrite_description"] == result
    assert transcript["final_description"] == result
