#!/usr/bin/env python3
"""Run the eval + improve loop until all pass or max iterations reached.

Combines run_eval.py and improve_description.py in a loop, tracking history
and returning the best description found. Supports train/test split to prevent
overfitting.
"""

import argparse
import json
import random
import sys
import tempfile
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from scripts.generate_report import generate_html
from scripts.improve_description import improve_description
from scripts.run_eval import find_project_root, run_eval
from scripts.utils import parse_skill_md


def split_eval_set(
    eval_set: list[dict], holdout: float, seed: int = 42
) -> tuple[list[dict], list[dict]]:
    """Split eval set into train and test sets, stratified by should_trigger."""
    random.seed(seed)

    # Separate by should_trigger
    trigger = [e for e in eval_set if e["should_trigger"]]
    no_trigger = [e for e in eval_set if not e["should_trigger"]]

    # Shuffle each group
    random.shuffle(trigger)
    random.shuffle(no_trigger)

    # Calculate split points
    n_trigger_test = max(1, int(len(trigger) * holdout))
    n_no_trigger_test = max(1, int(len(no_trigger) * holdout))

    # Split
    test_set = trigger[:n_trigger_test] + no_trigger[:n_no_trigger_test]
    train_set = trigger[n_trigger_test:] + no_trigger[n_no_trigger_test:]

    return train_set, test_set


def _summarize_results(results: list[dict]) -> dict[str, int]:
    passed = sum(1 for result in results if result["pass"])
    return {"passed": passed, "failed": len(results) - passed, "total": len(results)}


def _split_results(
    results: list[dict], train_set: list[dict]
) -> tuple[list[dict], list[dict]]:
    train_queries = {item["query"] for item in train_set}
    train_results = [item for item in results if item["query"] in train_queries]
    test_results = [item for item in results if item["query"] not in train_queries]
    return train_results, test_results


def _build_partition(results: list[dict]) -> dict:
    return {"results": results, "summary": _summarize_results(results)}


def _build_history_entry(
    iteration: int,
    description: str,
    train_results: list[dict],
    test_results: list[dict] | None,
) -> tuple[dict, dict, dict | None]:
    train_partition = _build_partition(train_results)
    test_partition = (
        _build_partition(test_results) if test_results is not None else None
    )
    train_summary = train_partition["summary"]
    test_summary = test_partition["summary"] if test_partition else None
    entry = {
        "iteration": iteration,
        "description": description,
        "train_passed": train_summary["passed"],
        "train_failed": train_summary["failed"],
        "train_total": train_summary["total"],
        "train_results": train_partition["results"],
        "test_passed": test_summary["passed"] if test_summary else None,
        "test_failed": test_summary["failed"] if test_summary else None,
        "test_total": test_summary["total"] if test_summary else None,
        "test_results": test_partition["results"] if test_partition else None,
        # Keep the original aliases for older report consumers.
        "passed": train_summary["passed"],
        "failed": train_summary["failed"],
        "total": train_summary["total"],
        "results": train_partition["results"],
    }
    return entry, train_partition, test_partition


def _write_live_report(
    path: Path,
    *,
    original_description: str,
    current_description: str,
    iteration_count: int,
    holdout: float,
    train_size: int,
    test_size: int,
    history: list[dict],
    skill_name: str,
) -> None:
    partial_output = {
        "original_description": original_description,
        "best_description": current_description,
        "best_score": "in progress",
        "iterations_run": iteration_count,
        "holdout": holdout,
        "train_size": train_size,
        "test_size": test_size,
        "history": history,
    }
    path.write_text(
        generate_html(partial_output, auto_refresh=True, skill_name=skill_name),
        encoding="utf-8",
    )


def _print_eval_stats(label: str, results: list[dict], elapsed: float) -> None:
    positive = [result for result in results if result["should_trigger"]]
    negative = [result for result in results if not result["should_trigger"]]
    true_positive = sum(result["triggers"] for result in positive)
    positive_runs = sum(result["runs"] for result in positive)
    false_negative = positive_runs - true_positive
    false_positive = sum(result["triggers"] for result in negative)
    negative_runs = sum(result["runs"] for result in negative)
    true_negative = negative_runs - false_positive
    total = true_positive + true_negative + false_positive + false_negative
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive > 0
        else 1.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative > 0
        else 1.0
    )
    accuracy = (true_positive + true_negative) / total if total > 0 else 0.0
    print(
        f"{label}: {true_positive + true_negative}/{total} correct, "
        f"precision={precision:.0%} recall={recall:.0%} "
        f"accuracy={accuracy:.0%} ({elapsed:.1f}s)",
        file=sys.stderr,
    )
    for result in results:
        status = "PASS" if result["pass"] else "FAIL"
        rate = f"{result['triggers']}/{result['runs']}"
        print(
            f"  [{status}] rate={rate} expected={result['should_trigger']}: "
            f"{result['query'][:60]}",
            file=sys.stderr,
        )


def _select_best_iteration(history: list[dict], has_test_set: bool) -> tuple[dict, str]:
    if has_test_set:
        best = max(history, key=lambda item: item["test_passed"] or 0)
        score = f"{best['test_passed']}/{best['test_total']}"
    else:
        best = max(history, key=lambda item: item["train_passed"])
        score = f"{best['train_passed']}/{best['train_total']}"
    return best, score


def _blind_test_scores(history: list[dict]) -> list[dict]:
    return [
        {key: value for key, value in entry.items() if not key.startswith("test_")}
        for entry in history
    ]


@dataclass(frozen=True)
class _LoopContext:
    project_root: Path
    skill_name: str
    original_description: str
    skill_content: str
    train_set: list[dict]
    test_set: list[dict]
    num_workers: int
    timeout: int
    runs_per_query: int
    trigger_threshold: float
    holdout: float
    model: str
    verbose: bool
    live_report_path: Path | None


def _log_iteration_header(
    iteration: int, max_iterations: int, description: str
) -> None:
    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"Iteration {iteration}/{max_iterations}", file=sys.stderr)
    print(f"Description: {description}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)


def _evaluate_iteration(
    context: _LoopContext,
    iteration: int,
    description: str,
    history: list[dict],
) -> dict:
    started = time.time()
    all_results = run_eval(
        eval_set=context.train_set + context.test_set,
        skill_name=context.skill_name,
        description=description,
        num_workers=context.num_workers,
        timeout=context.timeout,
        project_root=context.project_root,
        runs_per_query=context.runs_per_query,
        trigger_threshold=context.trigger_threshold,
        model=context.model,
    )
    elapsed = time.time() - started
    train_result_list, test_result_list = _split_results(
        all_results["results"], context.train_set
    )
    entry, train_results, test_results = _build_history_entry(
        iteration,
        description,
        train_result_list,
        test_result_list if context.test_set else None,
    )
    history.append(entry)

    if context.live_report_path:
        _write_live_report(
            context.live_report_path,
            original_description=context.original_description,
            current_description=description,
            iteration_count=len(history),
            holdout=context.holdout,
            train_size=len(context.train_set),
            test_size=len(context.test_set),
            history=history,
            skill_name=context.skill_name,
        )
    if context.verbose:
        _print_eval_stats("Train", train_results["results"], elapsed)
        if test_results:
            _print_eval_stats("Test ", test_results["results"], 0)
    return train_results


def _improve_after_iteration(
    context: _LoopContext,
    description: str,
    train_results: dict,
    history: list[dict],
    log_dir: Path | None,
    iteration: int,
) -> str:
    if context.verbose:
        print("\nImproving description...", file=sys.stderr)
    started = time.time()
    improved = improve_description(
        skill_name=context.skill_name,
        skill_content=context.skill_content,
        current_description=description,
        eval_results=train_results,
        history=_blind_test_scores(history),
        model=context.model,
        log_dir=log_dir,
        iteration=iteration,
    )
    if context.verbose:
        print(f"Proposed ({time.time() - started:.1f}s): {improved}", file=sys.stderr)
    return improved


def _build_loop_output(
    context: _LoopContext,
    history: list[dict],
    current_description: str,
    exit_reason: str,
) -> dict:
    best, best_score = _select_best_iteration(history, bool(context.test_set))
    if context.verbose:
        print(f"\nExit reason: {exit_reason}", file=sys.stderr)
        print(
            f"Best score: {best_score} (iteration {best['iteration']})", file=sys.stderr
        )

    return {
        "exit_reason": exit_reason,
        "original_description": context.original_description,
        "best_description": best["description"],
        "best_score": best_score,
        "best_train_score": f"{best['train_passed']}/{best['train_total']}",
        "best_test_score": (
            f"{best['test_passed']}/{best['test_total']}" if context.test_set else None
        ),
        "final_description": current_description,
        "iterations_run": len(history),
        "holdout": context.holdout,
        "train_size": len(context.train_set),
        "test_size": len(context.test_set),
        "history": history,
    }


def run_loop(
    eval_set: list[dict],
    skill_path: Path,
    description_override: str | None,
    num_workers: int,
    timeout: int,
    max_iterations: int,
    runs_per_query: int,
    trigger_threshold: float,
    holdout: float,
    model: str,
    verbose: bool,
    live_report_path: Path | None = None,
    log_dir: Path | None = None,
) -> dict:
    """Run evaluations, improve the description, and return the best result."""
    name, original_description, content = parse_skill_md(skill_path)
    current_description = description_override or original_description
    if holdout > 0:
        train_set, test_set = split_eval_set(eval_set, holdout)
        if verbose:
            print(
                f"Split: {len(train_set)} train, {len(test_set)} test "
                f"(holdout={holdout})",
                file=sys.stderr,
            )
    else:
        train_set, test_set = eval_set, []

    context = _LoopContext(
        project_root=find_project_root(),
        skill_name=name,
        original_description=original_description,
        skill_content=content,
        train_set=train_set,
        test_set=test_set,
        num_workers=num_workers,
        timeout=timeout,
        runs_per_query=runs_per_query,
        trigger_threshold=trigger_threshold,
        holdout=holdout,
        model=model,
        verbose=verbose,
        live_report_path=live_report_path,
    )
    history: list[dict] = []
    exit_reason = "unknown"
    for iteration in range(1, max_iterations + 1):
        if verbose:
            _log_iteration_header(iteration, max_iterations, current_description)
        train_results = _evaluate_iteration(
            context, iteration, current_description, history
        )
        if train_results["summary"]["failed"] == 0:
            exit_reason = f"all_passed (iteration {iteration})"
            if verbose:
                print(
                    f"\nAll train queries passed on iteration {iteration}!",
                    file=sys.stderr,
                )
            break
        if iteration == max_iterations:
            exit_reason = f"max_iterations ({max_iterations})"
            if verbose:
                print(f"\nMax iterations reached ({max_iterations}).", file=sys.stderr)
            break
        current_description = _improve_after_iteration(
            context,
            current_description,
            train_results,
            history,
            log_dir,
            iteration,
        )

    return _build_loop_output(context, history, current_description, exit_reason)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run eval + improve loop")
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON file")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument(
        "--description", default=None, help="Override starting description"
    )
    parser.add_argument(
        "--num-workers", type=int, default=10, help="Number of parallel workers"
    )
    parser.add_argument(
        "--timeout", type=int, default=30, help="Timeout per query in seconds"
    )
    parser.add_argument(
        "--max-iterations", type=int, default=5, help="Max improvement iterations"
    )
    parser.add_argument(
        "--runs-per-query", type=int, default=3, help="Number of runs per query"
    )
    parser.add_argument(
        "--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold"
    )
    parser.add_argument(
        "--holdout",
        type=float,
        default=0.4,
        help="Fraction of eval set to hold out for testing (0 to disable)",
    )
    parser.add_argument("--model", required=True, help="Model for improvement")
    parser.add_argument(
        "--verbose", action="store_true", help="Print progress to stderr"
    )
    parser.add_argument(
        "--report",
        default="auto",
        help="Generate HTML report at this path (default: 'auto' for temp file, 'none' to disable)",
    )
    parser.add_argument(
        "--results-dir",
        default=None,
        help="Save all outputs (results.json, report.html, log.txt) to a timestamped subdirectory here",
    )
    return parser


def _open_live_report(report_option: str, skill_path: Path) -> Path | None:
    if report_option == "none":
        return None
    if report_option == "auto":
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        report_path = (
            Path(tempfile.gettempdir())
            / f"skill_description_report_{skill_path.name}_{timestamp}.html"
        )
    else:
        report_path = Path(report_option)
    report_path.write_text(
        "<html><body><h1>Starting optimization loop...</h1><meta http-equiv='refresh' content='5'></body></html>"
    )
    webbrowser.open(str(report_path))
    return report_path


def _create_results_dir(results_dir_option: str | None) -> Path | None:
    if not results_dir_option:
        return None
    timestamp = time.strftime("%Y-%m-%d_%H%M%S")
    results_dir = Path(results_dir_option) / timestamp
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir


def _write_run_outputs(
    output: dict,
    skill_name: str,
    results_dir: Path | None,
    live_report_path: Path | None,
) -> None:
    json_output = json.dumps(output, indent=2)
    print(json_output)
    if results_dir:
        (results_dir / "results.json").write_text(json_output)

    if live_report_path:
        final_html = generate_html(output, auto_refresh=False, skill_name=skill_name)
        live_report_path.write_text(final_html)
        print(f"\nReport: {live_report_path}", file=sys.stderr)
        if results_dir:
            (results_dir / "report.html").write_text(final_html)

    if results_dir:
        print(f"Results saved to: {results_dir}", file=sys.stderr)


def main() -> None:
    args = _build_argument_parser().parse_args()
    eval_set = json.loads(Path(args.eval_set).read_text())
    skill_path = Path(args.skill_path)
    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, _, _ = parse_skill_md(skill_path)
    live_report_path = _open_live_report(args.report, skill_path)
    results_dir = _create_results_dir(args.results_dir)
    output = run_loop(
        eval_set=eval_set,
        skill_path=skill_path,
        description_override=args.description,
        num_workers=args.num_workers,
        timeout=args.timeout,
        max_iterations=args.max_iterations,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        holdout=args.holdout,
        model=args.model,
        verbose=args.verbose,
        live_report_path=live_report_path,
        log_dir=results_dir / "logs" if results_dir else None,
    )
    _write_run_outputs(output, name, results_dir, live_report_path)


if __name__ == "__main__":
    main()
