#!/usr/bin/env python3
"""Generate an HTML report from run_loop.py output."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from string import Template
from typing import Any

_TEMPLATE_PATH = Path(__file__).with_name("report_template.html")
_LEGEND = """
    <div class="legend">
        <span style="font-weight:600">Query columns:</span>
        <span class="legend-item"><span class="legend-swatch swatch-positive"></span> Should trigger</span>
        <span class="legend-item"><span class="legend-swatch swatch-negative"></span> Should NOT trigger</span>
        <span class="legend-item"><span class="legend-swatch swatch-train"></span> Train</span>
        <span class="legend-item"><span class="legend-swatch swatch-test"></span> Test</span>
    </div>
"""
_TABLE_START = """
    <div class="table-container">
    <table>
        <thead>
            <tr>
                <th>Iter</th>
                <th>Train</th>
                <th>Test</th>
                <th class="query-col">Description</th>
"""
_TABLE_BODY = """            </tr>
        </thead>
        <tbody>
"""
_TABLE_END = """        </tbody>
    </table>
    </div>
"""


def _query_columns(history: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    if not history:
        return [], []
    first_iteration = history[0]
    train_results = first_iteration.get(
        "train_results", first_iteration.get("results", [])
    )
    test_results = first_iteration.get("test_results") or []
    train_queries = [
        {"query": result["query"], "should_trigger": result.get("should_trigger", True)}
        for result in train_results
    ]
    test_queries = [
        {"query": result["query"], "should_trigger": result.get("should_trigger", True)}
        for result in test_results
    ]
    return train_queries, test_queries


def _aggregate_runs(results: list[dict[str, Any]] | None) -> tuple[int, int]:
    correct = 0
    total = 0
    for result in results or []:
        runs = result.get("runs", 0)
        triggers = result.get("triggers", 0)
        total += runs
        correct += triggers if result.get("should_trigger", True) else runs - triggers
    return correct, total


def _score_class(correct: int, total: int) -> str:
    if total == 0:
        return "score-bad"
    ratio = correct / total
    if ratio >= 0.8:
        return "score-good"
    if ratio >= 0.5:
        return "score-ok"
    return "score-bad"


def _render_summary(data: dict[str, Any]) -> str:
    score_kind = "(test)" if data.get("best_test_score") else "(train)"
    return f"""
    <div class="summary">
        <p><strong>Original:</strong> {html.escape(data.get("original_description", "N/A"))}</p>
        <p class="best"><strong>Best:</strong> {html.escape(data.get("best_description", "N/A"))}</p>
        <p><strong>Best Score:</strong> {data.get("best_score", "N/A")} {score_kind}</p>
        <p><strong>Iterations:</strong> {data.get("iterations_run", 0)} | <strong>Train:</strong> {data.get("train_size", "?")} | <strong>Test:</strong> {data.get("test_size", "?")}</p>
    </div>
"""


def _render_query_headers(queries: list[dict], *, test: bool = False) -> str:
    test_class = "test-col " if test else ""
    return "".join(
        f'                <th class="{test_class}'
        f'{"positive-col" if query["should_trigger"] else "negative-col"}">'
        f"{html.escape(query['query'])}</th>\n"
        for query in queries
    )


def _render_result_cell(
    query: dict,
    results_by_query: dict[str, dict[str, Any]],
    *,
    test: bool = False,
) -> str:
    result = results_by_query.get(query["query"], {})
    passed = result.get("pass", False)
    icon = "✓" if passed else "✗"
    css_class = "pass" if passed else "fail"
    test_class = " test-result" if test else ""
    return (
        f'                <td class="result{test_class} {css_class}">'
        f'{icon}<span class="rate">{result.get("triggers", 0)}/'
        f"{result.get('runs', 0)}</span></td>\n"
    )


def _render_iteration(
    iteration: dict[str, Any],
    train_queries: list[dict],
    test_queries: list[dict],
    best_iteration: Any,
) -> str:
    number = iteration.get("iteration", "?")
    description = html.escape(iteration.get("description", ""))
    train_results = iteration.get("train_results", iteration.get("results", [])) or []
    test_results = iteration.get("test_results") or []
    train_by_query = {result["query"]: result for result in train_results}
    test_by_query = {result["query"]: result for result in test_results}
    train_correct, train_runs = _aggregate_runs(train_results)
    test_correct, test_runs = _aggregate_runs(test_results)
    row_class = "best-row" if number == best_iteration else ""
    cells = "".join(
        _render_result_cell(query, train_by_query) for query in train_queries
    )
    cells += "".join(
        _render_result_cell(query, test_by_query, test=True) for query in test_queries
    )
    return (
        f'            <tr class="{row_class}">\n'
        f"                <td>{number}</td>\n"
        f'                <td><span class="score {_score_class(train_correct, train_runs)}">'
        f"{train_correct}/{train_runs}</span></td>\n"
        f'                <td><span class="score {_score_class(test_correct, test_runs)}">'
        f"{test_correct}/{test_runs}</span></td>\n"
        f'                <td class="description">{description}</td>\n'
        f"{cells}            </tr>\n"
    )


def _render_table(
    history: list[dict[str, Any]],
    train_queries: list[dict],
    test_queries: list[dict],
) -> str:
    if test_queries:
        best_iteration = max(
            history, key=lambda item: item.get("test_passed") or 0
        ).get("iteration")
    else:
        best_iteration = max(
            history,
            key=lambda item: item.get("train_passed", item.get("passed", 0)),
        ).get("iteration")

    parts = [_TABLE_START]
    parts.append(_render_query_headers(train_queries))
    parts.append(_render_query_headers(test_queries, test=True))
    parts.append(_TABLE_BODY)
    parts.extend(
        _render_iteration(entry, train_queries, test_queries, best_iteration)
        for entry in history
    )
    parts.append(_TABLE_END)
    return "".join(parts)


def generate_html(
    data: dict[str, Any], auto_refresh: bool = False, skill_name: str = ""
) -> str:
    """Render loop output with a separate static HTML/CSS template."""
    history = data.get("history", [])
    train_queries, test_queries = _query_columns(history)
    title_prefix = html.escape(skill_name + " — ") if skill_name else ""
    refresh_tag = (
        '    <meta http-equiv="refresh" content="5">\n' if auto_refresh else ""
    )
    template = Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))
    return template.substitute(
        refresh_tag=refresh_tag,
        title_prefix=title_prefix,
        summary=_render_summary(data),
        legend=_LEGEND,
        table=_render_table(history, train_queries, test_queries),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate HTML report from run_loop output"
    )
    parser.add_argument(
        "input", help="Path to JSON output from run_loop.py (or - for stdin)"
    )
    parser.add_argument(
        "-o", "--output", default=None, help="Output HTML file (default: stdout)"
    )
    parser.add_argument(
        "--skill-name", default="", help="Skill name to include in the report title"
    )
    args = parser.parse_args()

    if args.input == "-":
        data = json.load(sys.stdin)
    else:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))

    output = generate_html(data, skill_name=args.skill_name)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
