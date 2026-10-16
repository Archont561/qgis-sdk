#!/usr/bin/env python3
"""
Aggregate individual run results into benchmark summary statistics.

Reads grading.json files from run directories and produces:
- run_summary with mean, stddev, min, max for each metric
- delta between with_skill and without_skill configurations

Usage:
    python aggregate_benchmark.py <benchmark_dir>

Example:
    python aggregate_benchmark.py benchmarks/2026-01-15T10-30-00/

The script supports two directory layouts:

    Workspace layout (from skill-creator iterations):
    <benchmark_dir>/
    └── eval-N/
        ├── with_skill/
        │   ├── run-1/grading.json
        │   └── run-2/grading.json
        └── without_skill/
            ├── run-1/grading.json
            └── run-2/grading.json

    Legacy layout (with runs/ subdirectory):
    <benchmark_dir>/
    └── runs/
        └── eval-N/
            ├── with_skill/
            │   └── run-1/grading.json
            └── without_skill/
                └── run-1/grading.json
"""

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path


def calculate_stats(values: list[float]) -> dict:
    """Calculate mean, stddev, min, max for a list of values."""
    if not values:
        return {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}

    n = len(values)
    mean = sum(values) / n

    if n > 1:
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        stddev = math.sqrt(variance)
    else:
        stddev = 0.0

    return {
        "mean": round(mean, 4),
        "stddev": round(stddev, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _find_search_directory(benchmark_dir: Path) -> Path | None:
    runs_dir = benchmark_dir / "runs"
    if runs_dir.exists():
        return runs_dir
    if list(benchmark_dir.glob("eval-*")):
        return benchmark_dir
    print(f"No eval directories found in {benchmark_dir} or {runs_dir}")
    return None


def _load_eval_id(eval_dir: Path, fallback: int) -> int:
    metadata_path = eval_dir / "eval_metadata.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            return metadata.get("eval_id", fallback)
        except (json.JSONDecodeError, OSError):
            return fallback
    try:
        return int(eval_dir.name.split("-")[1])
    except ValueError:
        return fallback


def _load_grading(grading_file: Path) -> dict | None:
    if not grading_file.exists():
        print(f"Warning: grading.json not found in {grading_file.parent}")
        return None
    try:
        return json.loads(grading_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        print(f"Warning: Invalid JSON in {grading_file}: {error}")
        return None


def _load_timing(run_dir: Path) -> dict:
    timing_file = run_dir / "timing.json"
    if not timing_file.exists():
        return {}
    try:
        return json.loads(timing_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _extract_run_metrics(
    grading: dict, run_dir: Path, eval_id: int, run_number: int
) -> dict:
    summary = grading.get("summary", {})
    timing = grading.get("timing", {})
    result = {
        "eval_id": eval_id,
        "run_number": run_number,
        "pass_rate": summary.get("pass_rate", 0.0),
        "passed": summary.get("passed", 0),
        "failed": summary.get("failed", 0),
        "total": summary.get("total", 0),
        "time_seconds": timing.get("total_duration_seconds", 0.0),
    }
    if result["time_seconds"] == 0.0:
        timing_data = _load_timing(run_dir)
        result["time_seconds"] = timing_data.get("total_duration_seconds", 0.0)
        result["tokens"] = timing_data.get("total_tokens", 0)

    metrics = grading.get("execution_metrics", {})
    result["tool_calls"] = metrics.get("total_tool_calls", 0)
    if not result.get("tokens"):
        result["tokens"] = metrics.get("output_chars", 0)
    result["errors"] = metrics.get("errors_encountered", 0)

    expectations = grading.get("expectations", [])
    for expectation in expectations:
        if "text" not in expectation or "passed" not in expectation:
            print(
                f"Warning: expectation in {run_dir / 'grading.json'} missing "
                f"required fields (text, passed, evidence): {expectation}"
            )
    result["expectations"] = expectations

    notes_summary = grading.get("user_notes_summary", {})
    result["notes"] = [
        *notes_summary.get("uncertainties", []),
        *notes_summary.get("needs_review", []),
        *notes_summary.get("workarounds", []),
    ]
    return result


def _load_run_result(run_dir: Path, eval_id: int) -> dict | None:
    run_number = int(run_dir.name.split("-")[1])
    grading = _load_grading(run_dir / "grading.json")
    if grading is None:
        return None
    return _extract_run_metrics(grading, run_dir, eval_id, run_number)


def load_run_results(benchmark_dir: Path) -> dict[str, list[dict]]:
    """Load normalized run records from workspace or legacy benchmark layouts."""
    search_dir = _find_search_directory(benchmark_dir)
    if search_dir is None:
        return {}

    results: dict[str, list[dict]] = {}
    for eval_index, eval_dir in enumerate(sorted(search_dir.glob("eval-*"))):
        eval_id = _load_eval_id(eval_dir, eval_index)
        for config_dir in sorted(eval_dir.iterdir()):
            if not config_dir.is_dir() or not list(config_dir.glob("run-*")):
                continue
            config_results = results.setdefault(config_dir.name, [])
            for run_dir in sorted(config_dir.glob("run-*")):
                run_result = _load_run_result(run_dir, eval_id)
                if run_result is not None:
                    config_results.append(run_result)
    return results


def _aggregate_configuration(runs: list[dict]) -> dict:
    if not runs:
        empty_stats = {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}
        return {
            "pass_rate": empty_stats.copy(),
            "time_seconds": empty_stats.copy(),
            "tokens": {"mean": 0, "stddev": 0, "min": 0, "max": 0},
        }

    return {
        "pass_rate": calculate_stats([run["pass_rate"] for run in runs]),
        "time_seconds": calculate_stats([run["time_seconds"] for run in runs]),
        "tokens": calculate_stats([run.get("tokens", 0) for run in runs]),
    }


def _configuration_delta(run_summary: dict, configs: list[str]) -> dict[str, str]:
    primary_name = configs[0] if configs else None
    baseline_name = configs[1] if len(configs) >= 2 else None
    primary = run_summary.get(primary_name, {}) if primary_name else {}
    baseline = run_summary.get(baseline_name, {}) if baseline_name else {}
    delta_pass_rate = primary.get("pass_rate", {}).get("mean", 0) - baseline.get(
        "pass_rate", {}
    ).get("mean", 0)
    delta_time = primary.get("time_seconds", {}).get("mean", 0) - baseline.get(
        "time_seconds", {}
    ).get("mean", 0)
    delta_tokens = primary.get("tokens", {}).get("mean", 0) - baseline.get(
        "tokens", {}
    ).get("mean", 0)
    return {
        "pass_rate": f"{delta_pass_rate:+.2f}",
        "time_seconds": f"{delta_time:+.1f}",
        "tokens": f"{delta_tokens:+.0f}",
    }


def aggregate_results(results: dict) -> dict:
    """Aggregate run records into per-configuration statistics and deltas."""
    configs = list(results)
    run_summary = {
        config: _aggregate_configuration(results.get(config, [])) for config in configs
    }
    run_summary["delta"] = _configuration_delta(run_summary, configs)
    return run_summary


def _benchmark_run(config: str, result: dict) -> dict:
    return {
        "eval_id": result["eval_id"],
        "configuration": config,
        "run_number": result["run_number"],
        "result": {
            "pass_rate": result["pass_rate"],
            "passed": result["passed"],
            "failed": result["failed"],
            "total": result["total"],
            "time_seconds": result["time_seconds"],
            "tokens": result.get("tokens", 0),
            "tool_calls": result.get("tool_calls", 0),
            "errors": result.get("errors", 0),
        },
        "expectations": result["expectations"],
        "notes": result["notes"],
    }


def _benchmark_metadata(
    results: dict[str, list[dict]], skill_name: str, skill_path: str
) -> dict:
    eval_ids = sorted({run["eval_id"] for runs in results.values() for run in runs})
    return {
        "skill_name": skill_name or "<skill-name>",
        "skill_path": skill_path or "<path/to/skill>",
        "executor_model": "<model-name>",
        "analyzer_model": "<model-name>",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evals_run": eval_ids,
        "runs_per_configuration": 3,
    }


def generate_benchmark(
    benchmark_dir: Path, skill_name: str = "", skill_path: str = ""
) -> dict:
    """Generate complete benchmark data from persisted run records."""
    results = load_run_results(benchmark_dir)
    runs = [
        _benchmark_run(config, result)
        for config, config_runs in results.items()
        for result in config_runs
    ]
    return {
        "metadata": _benchmark_metadata(results, skill_name, skill_path),
        "runs": runs,
        "run_summary": aggregate_results(results),
        "notes": [],  # To be filled by analyzer
    }


def _summary_metric_row(
    label: str,
    first: dict,
    second: dict,
    delta: dict,
    metric: str,
    *,
    scale: int = 1,
    precision: int = 0,
    unit: str = "",
    delta_unit: str = "",
) -> str:
    first_value = first.get(metric, {})
    second_value = second.get(metric, {})

    def format_stats(stats: dict) -> str:
        mean = stats.get("mean", 0) * scale
        stddev = stats.get("stddev", 0) * scale
        return f"{mean:.{precision}f}{unit} ± {stddev:.{precision}f}{unit}"

    delta_value = f"{delta.get(metric, '—')}{delta_unit}"
    return (
        f"| {label} | {format_stats(first_value)} | "
        f"{format_stats(second_value)} | {delta_value} |"
    )


def _summary_table_lines(first: dict, second: dict, delta: dict) -> list[str]:
    return [
        _summary_metric_row(
            "Pass Rate", first, second, delta, "pass_rate", scale=100, unit="%"
        ),
        _summary_metric_row(
            "Time",
            first,
            second,
            delta,
            "time_seconds",
            precision=1,
            unit="s",
            delta_unit="s",
        ),
        _summary_metric_row("Tokens", first, second, delta, "tokens", precision=0),
    ]


def _config_label(config: str) -> str:
    return config.replace("_", " ").title()


def generate_markdown(benchmark: dict) -> str:
    """Generate human-readable benchmark.md from benchmark data."""
    metadata = benchmark["metadata"]
    run_summary = benchmark["run_summary"]
    configs = [key for key in run_summary if key != "delta"]
    config_a = configs[0] if configs else "config_a"
    config_b = configs[1] if len(configs) >= 2 else "config_b"
    first = run_summary.get(config_a, {})
    second = run_summary.get(config_b, {})
    delta = run_summary.get("delta", {})
    lines = [
        f"# Skill Benchmark: {metadata['skill_name']}",
        "",
        f"**Model**: {metadata['executor_model']}",
        f"**Date**: {metadata['timestamp']}",
        f"**Evals**: {', '.join(map(str, metadata['evals_run']))} ({metadata['runs_per_configuration']} runs each per configuration)",
        "",
        "## Summary",
        "",
        f"| Metric | {_config_label(config_a)} | {_config_label(config_b)} | Delta |",
        "|--------|------------|---------------|-------|",
        *_summary_table_lines(first, second, delta),
    ]

    if benchmark.get("notes"):
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in benchmark["notes"])
    return "\n".join(lines)


def _write_benchmark_files(output_json: Path, benchmark: dict) -> None:
    output_md = output_json.with_suffix(".md")
    with output_json.open("w") as output_file:
        json.dump(benchmark, output_file, indent=2)
    print(f"Generated: {output_json}")

    output_md.write_text(generate_markdown(benchmark), encoding="utf-8")
    print(f"Generated: {output_md}")


def _print_benchmark_summary(benchmark: dict) -> None:
    run_summary = benchmark["run_summary"]
    configs = [key for key in run_summary if key != "delta"]
    delta = run_summary.get("delta", {})
    print("\nSummary:")
    for config in configs:
        pass_rate = run_summary[config]["pass_rate"]["mean"]
        print(f"  {_config_label(config)}: {pass_rate * 100:.1f}% pass rate")
    print(f"  Delta:         {delta.get('pass_rate', '—')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate benchmark run results into summary statistics"
    )
    parser.add_argument(
        "benchmark_dir", type=Path, help="Path to the benchmark directory"
    )
    parser.add_argument(
        "--skill-name", default="", help="Name of the skill being benchmarked"
    )
    parser.add_argument(
        "--skill-path", default="", help="Path to the skill being benchmarked"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output path for benchmark.json (default: <benchmark_dir>/benchmark.json)",
    )
    args = parser.parse_args()

    if not args.benchmark_dir.exists():
        print(f"Directory not found: {args.benchmark_dir}")
        sys.exit(1)

    benchmark = generate_benchmark(args.benchmark_dir, args.skill_name, args.skill_path)
    output_json = args.output or (args.benchmark_dir / "benchmark.json")
    _write_benchmark_files(output_json, benchmark)
    _print_benchmark_summary(benchmark)


if __name__ == "__main__":
    main()
