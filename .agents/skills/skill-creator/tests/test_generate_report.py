from __future__ import annotations

from scripts.generate_report import generate_html


def test_report_renders_escaped_descriptions_and_train_results() -> None:
    output = generate_html(
        {
            "original_description": "<old>description</old>",
            "best_description": "<best>description</best>",
            "best_score": "0/1",
            "best_test_score": None,
            "best_train_score": "0/1",
            "iterations_run": 1,
            "train_size": 1,
            "test_size": 0,
            "history": [
                {
                    "iteration": 1,
                    "description": "<script>alert(1)</script>",
                    "passed": 0,
                    "total": 1,
                    "train_results": [
                        {
                            "query": "open <layer>",
                            "should_trigger": True,
                            "pass": False,
                            "triggers": 0,
                            "runs": 1,
                        }
                    ],
                    "test_results": [],
                }
            ],
        },
        skill_name="<demo>",
    )

    assert "&lt;demo&gt;" in output
    assert "&lt;old&gt;description&lt;/old&gt;" in output
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in output
    assert "open &lt;layer&gt;" in output
    assert "0/1" in output
    assert "open &lt;layer&gt;</th>\n" in output


def test_report_handles_no_holdout_test_results() -> None:
    output = generate_html(
        {
            "best_description": "description",
            "best_score": "1/1",
            "best_test_score": None,
            "history": [
                {
                    "iteration": 1,
                    "description": "description",
                    "passed": 1,
                    "total": 1,
                    "train_results": [
                        {
                            "query": "run",
                            "should_trigger": True,
                            "pass": True,
                            "triggers": 1,
                            "runs": 1,
                        }
                    ],
                    "test_results": None,
                }
            ],
        }
    )

    assert "Skill Description Optimization" in output
    assert "1/1" in output
