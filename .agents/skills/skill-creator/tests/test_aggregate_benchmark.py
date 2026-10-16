from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.aggregate_benchmark import (
    aggregate_results,
    generate_benchmark,
    generate_markdown,
    load_run_results,
)


def _write_run(
    run_dir: Path,
    *,
    pass_rate: float,
    timing: dict[str, Any] | None = None,
    timing_file: dict[str, Any] | None = None,
) -> None:
    run_dir.mkdir(parents=True)
    grading = {
        "summary": {"pass_rate": pass_rate, "passed": 3, "failed": 1, "total": 4},
        "timing": timing or {},
        "execution_metrics": {
            "total_tool_calls": 4,
            "output_chars": 80,
            "errors_encountered": 0,
        },
        "expectations": [{"text": "output exists", "passed": True, "evidence": "file"}],
        "user_notes_summary": {
            "uncertainties": ["review"],
            "needs_review": [],
            "workarounds": [],
        },
    }
    (run_dir / "grading.json").write_text(json.dumps(grading), encoding="utf-8")
    if timing_file:
        (run_dir / "timing.json").write_text(json.dumps(timing_file), encoding="utf-8")


def test_load_and_aggregate_results_from_multiple_run_layouts(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval-1"
    eval_dir.mkdir()
    (eval_dir / "eval_metadata.json").write_text('{"eval_id": 17}', encoding="utf-8")
    _write_run(
        eval_dir / "with_skill" / "run-1",
        pass_rate=0.75,
        timing={"total_duration_seconds": 2.5},
    )
    _write_run(
        eval_dir / "without_skill" / "run-2",
        pass_rate=0.25,
        timing_file={"total_duration_seconds": 4.0, "total_tokens": 200},
    )

    results = load_run_results(tmp_path)

    assert results["with_skill"][0]["eval_id"] == 17
    assert results["with_skill"][0]["time_seconds"] == 2.5
    assert results["with_skill"][0]["tokens"] == 80
    assert results["without_skill"][0]["run_number"] == 2
    assert results["without_skill"][0]["time_seconds"] == 4.0
    assert results["without_skill"][0]["tokens"] == 200
    assert results["with_skill"][0]["notes"] == ["review"]

    summary = aggregate_results(results)
    assert summary["delta"]["pass_rate"] == "+0.50"
    markdown = generate_markdown(
        {
            "metadata": {
                "skill_name": "demo",
                "executor_model": "test-model",
                "timestamp": "2026-10-16T00:00:00Z",
                "evals_run": [17],
                "runs_per_configuration": 1,
            },
            "run_summary": summary,
            "notes": [],
        }
    )
    assert "# Skill Benchmark: demo" in markdown
    assert "75%" in markdown

    benchmark = generate_benchmark(
        tmp_path, skill_name="demo", skill_path="skills/demo"
    )
    assert benchmark["metadata"]["evals_run"] == [17]
    assert len(benchmark["runs"]) == 2
    assert benchmark["metadata"]["skill_name"] == "demo"


def test_aggregate_results_handles_empty_configurations() -> None:
    summary = aggregate_results({"with_skill": []})

    assert summary["with_skill"]["pass_rate"]["mean"] == 0.0
    assert summary["delta"] == {
        "pass_rate": "+0.00",
        "time_seconds": "+0.0",
        "tokens": "+0",
    }
