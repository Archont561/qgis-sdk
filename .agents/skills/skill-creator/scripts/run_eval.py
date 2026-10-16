#!/usr/bin/env python3
"""Run trigger evaluation for a skill description.

Tests whether a skill's description causes Claude to trigger (read the skill)
for a set of queries. Outputs results as JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.utils import parse_skill_md


@dataclass
class _TriggerStreamState:
    pending_tool_name: str | None = None
    accumulated_input_json: str = ""


def find_project_root() -> Path:
    """Find the project root by walking up from cwd looking for .claude/."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".claude").is_dir():
            return parent
    return current


def _write_skill_command(
    project_root: Path, command_name: str, skill_name: str, description: str
) -> Path:
    """Write the temporary command Claude discovers as the test skill."""
    command_dir = project_root / ".claude" / "commands"
    command_dir.mkdir(parents=True, exist_ok=True)
    command_file = command_dir / f"{command_name}.md"
    indented_description = "\n  ".join(description.split("\n"))
    command_file.write_text(
        f"---\n"
        f"description: |\n"
        f"  {indented_description}\n"
        f"---\n\n"
        f"# {skill_name}\n\n"
        f"This skill handles: {description}\n",
        encoding="utf-8",
    )
    return command_file


def _decode_stream_buffer(
    buffer: str, *, final: bool = False
) -> tuple[list[dict[str, Any]], str]:
    """Decode complete JSONL events, optionally consuming a final partial line."""
    lines = buffer.split("\n")
    remainder = "" if final else lines.pop()
    if final and lines[-1]:
        lines[-1] = lines[-1].strip()
    events: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events, remainder


def _iter_process_events(
    process: subprocess.Popen[bytes], timeout: int
) -> Iterator[dict[str, Any]]:
    """Yield JSONL events until the process exits or its deadline expires."""
    if process.stdout is None:
        raise RuntimeError("Claude CLI stdout pipe was not created")

    deadline = time.monotonic() + timeout
    buffer = ""
    while True:
        if process.poll() is not None:
            remaining = process.stdout.read()
            if remaining:
                buffer += remaining.decode("utf-8", errors="replace")
            events, _ = _decode_stream_buffer(buffer, final=True)
            yield from events
            return

        remaining_time = deadline - time.monotonic()
        if remaining_time <= 0:
            raise TimeoutError(f"Claude CLI timed out after {timeout} seconds")

        ready, _, _ = select.select([process.stdout], [], [], min(remaining_time, 1.0))
        if not ready:
            continue

        chunk = os.read(process.stdout.fileno(), 8192)
        if not chunk:
            continue
        buffer += chunk.decode("utf-8", errors="replace")
        events, buffer = _decode_stream_buffer(buffer)
        yield from events


def _trigger_from_event(
    event: dict[str, Any], command_name: str, state: _TriggerStreamState
) -> bool | None:
    """Return a decision when an event proves trigger or non-trigger behavior."""
    event_type = event.get("type")
    if event_type == "stream_event":
        stream_event = event.get("event", {})
        stream_type = stream_event.get("type", "")

        if stream_type == "content_block_start":
            content_block = stream_event.get("content_block", {})
            if content_block.get("type") == "tool_use":
                tool_name = content_block.get("name", "")
                if tool_name in ("Skill", "Read"):
                    state.pending_tool_name = tool_name
                    state.accumulated_input_json = ""
                else:
                    return False

        elif stream_type == "content_block_delta" and state.pending_tool_name:
            delta = stream_event.get("delta", {})
            if delta.get("type") == "input_json_delta":
                state.accumulated_input_json += delta.get("partial_json", "")
                if command_name in state.accumulated_input_json:
                    return True

        elif stream_type in ("content_block_stop", "message_stop"):
            if state.pending_tool_name:
                return command_name in state.accumulated_input_json
            if stream_type == "message_stop":
                return False

    elif event_type == "assistant":
        message = event.get("message", {})
        for content_item in message.get("content", []):
            if content_item.get("type") != "tool_use":
                continue
            tool_name = content_item.get("name", "")
            tool_input = content_item.get("input", {})
            if tool_name == "Skill":
                return command_name in tool_input.get("skill", "")
            if tool_name == "Read":
                return command_name in tool_input.get("file_path", "")
            return False
        return False

    elif event_type == "result":
        return False

    return None


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    """Stop a still-running CLI process and reap it."""
    if process.poll() is None:
        process.kill()
        process.wait()


def run_single_query(
    query: str,
    skill_name: str,
    skill_description: str,
    timeout: int,
    project_root: str,
    model: str | None = None,
) -> bool:
    """Run one query and return whether the temporary skill was triggered."""
    command_name = f"{skill_name}-skill-{uuid.uuid4().hex[:8]}"
    command_file = _write_skill_command(
        Path(project_root), command_name, skill_name, skill_description
    )
    command = [
        "claude",
        "-p",
        query,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
    ]
    if model:
        command.extend(["--model", model])
    environment = {
        key: value for key, value in os.environ.items() if key != "CLAUDECODE"
    }

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=project_root,
            env=environment,
        )
        try:
            state = _TriggerStreamState()
            for event in _iter_process_events(process, timeout):
                decision = _trigger_from_event(event, command_name, state)
                if decision is not None:
                    return decision

            if process.returncode not in (None, 0):
                raise subprocess.CalledProcessError(process.returncode, command)
            return False
        finally:
            _stop_process(process)
    finally:
        command_file.unlink(missing_ok=True)


def _run_workers(
    eval_set: list[dict[str, Any]],
    *,
    skill_name: str,
    description: str,
    num_workers: int,
    timeout: int,
    project_root: Path,
    runs_per_query: int,
    model: str | None,
) -> tuple[dict[str, list[bool]], dict[str, dict[str, Any]]]:
    """Execute each query concurrently and collect only successful outcomes."""
    query_triggers: dict[str, list[bool]] = {}
    query_items: dict[str, dict[str, Any]] = {}

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        future_to_info = {}
        for item in eval_set:
            for run_index in range(runs_per_query):
                future = executor.submit(
                    run_single_query,
                    item["query"],
                    skill_name,
                    description,
                    timeout,
                    str(project_root),
                    model,
                )
                future_to_info[future] = (item, run_index)

        for future in as_completed(future_to_info):
            item, _ = future_to_info[future]
            query = item["query"]
            query_items[query] = item
            query_triggers.setdefault(query, []).append(future.result())

    return query_triggers, query_items


def _make_query_result(
    query: str,
    item: dict[str, Any],
    triggers: list[bool],
    trigger_threshold: float,
) -> dict[str, Any]:
    trigger_count = sum(triggers)
    trigger_rate = trigger_count / len(triggers)
    should_trigger = item["should_trigger"]
    passed = (
        trigger_rate >= trigger_threshold
        if should_trigger
        else trigger_rate < trigger_threshold
    )
    return {
        "query": query,
        "should_trigger": should_trigger,
        "trigger_rate": trigger_rate,
        "triggers": trigger_count,
        "runs": len(triggers),
        "pass": passed,
    }


def _summarize_results(results: list[dict[str, Any]]) -> dict[str, int]:
    passed = sum(result["pass"] for result in results)
    return {"total": len(results), "passed": passed, "failed": len(results) - passed}


def run_eval(
    eval_set: list[dict[str, Any]],
    skill_name: str,
    description: str,
    num_workers: int,
    timeout: int,
    project_root: Path,
    runs_per_query: int = 1,
    trigger_threshold: float = 0.5,
    model: str | None = None,
) -> dict[str, Any]:
    """Run the full eval set and return per-query results and summary."""
    query_triggers, query_items = _run_workers(
        eval_set,
        skill_name=skill_name,
        description=description,
        num_workers=num_workers,
        timeout=timeout,
        project_root=project_root,
        runs_per_query=runs_per_query,
        model=model,
    )
    results = [
        _make_query_result(query, query_items[query], triggers, trigger_threshold)
        for query, triggers in query_triggers.items()
    ]
    return {
        "skill_name": skill_name,
        "description": description,
        "results": results,
        "summary": _summarize_results(results),
    }


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run trigger evaluation for a skill description"
    )
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON file")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument(
        "--description", default=None, help="Override description to test"
    )
    parser.add_argument(
        "--num-workers", type=int, default=10, help="Number of parallel workers"
    )
    parser.add_argument(
        "--timeout", type=int, default=30, help="Timeout per query in seconds"
    )
    parser.add_argument(
        "--runs-per-query", type=int, default=3, help="Number of runs per query"
    )
    parser.add_argument(
        "--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model to use for claude -p (default: user's configured model)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print progress to stderr"
    )
    return parser


def _load_skill_description(skill_path: Path) -> tuple[str, str]:
    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)
    name, description, _ = parse_skill_md(skill_path)
    return name, description


def _print_verbose_results(output: dict[str, Any], description: str) -> None:
    summary = output["summary"]
    print(f"Evaluating: {description}", file=sys.stderr)
    print(f"Results: {summary['passed']}/{summary['total']} passed", file=sys.stderr)
    for result in output["results"]:
        status = "PASS" if result["pass"] else "FAIL"
        rate = f"{result['triggers']}/{result['runs']}"
        print(
            f"  [{status}] rate={rate} expected={result['should_trigger']}: "
            f"{result['query'][:70]}",
            file=sys.stderr,
        )


def main() -> None:
    args = _build_argument_parser().parse_args()
    eval_set = json.loads(Path(args.eval_set).read_text(encoding="utf-8"))
    skill_path = Path(args.skill_path)
    name, original_description = _load_skill_description(skill_path)
    description = args.description or original_description
    output = run_eval(
        eval_set=eval_set,
        skill_name=name,
        description=description,
        num_workers=args.num_workers,
        timeout=args.timeout,
        project_root=find_project_root(),
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        model=args.model,
    )

    if args.verbose:
        _print_verbose_results(output, description)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
