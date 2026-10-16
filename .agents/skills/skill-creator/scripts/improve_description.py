#!/usr/bin/env python3
"""Improve a skill description based on eval results.

Takes eval results (from run_eval.py) and generates an improved description
by calling `claude -p` as a subprocess (same auth pattern as run_eval.py —
uses the session's Claude Code auth, no separate ANTHROPIC_API_KEY needed).
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from scripts.utils import parse_skill_md


def _call_claude(prompt: str, model: str | None, timeout: int = 300) -> str:
    """Run `claude -p` with the prompt on stdin and return the text response.

    Prompt goes over stdin (not argv) because it embeds the full SKILL.md
    body and can easily exceed comfortable argv length.
    """
    cmd = ["claude", "-p", "--output-format", "text"]
    if model:
        cmd.extend(["--model", model])

    # Remove CLAUDECODE env var to allow nesting claude -p inside a
    # Claude Code session. The guard is for interactive terminal conflicts;
    # programmatic subprocess usage is safe. Same pattern as run_eval.py.
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude -p exited {result.returncode}\nstderr: {result.stderr}"
        )
    return result.stdout


_PROMPT_HEADER = """You are optimizing a skill description for a Claude Code skill called "{skill_name}". A "skill" is sort of like a prompt, but with progressive disclosure -- there's a title and description that Claude sees when deciding whether to use the skill, and then if it does use the skill, it reads the .md file which has lots more details and potentially links to other resources in the skill folder like helper files and scripts and additional documentation or examples.

The description appears in Claude's "available_skills" list. When a user sends a query, Claude decides whether to invoke the skill based solely on the title and on this description. Your goal is to write a description that triggers for relevant queries, and doesn't trigger for irrelevant ones.

Here's the current description:
<current_description>
"{current_description}"
</current_description>

Current scores ({scores_summary}):
<scores_summary>
"""

_PROMPT_FOOTER = """</scores_summary>

Skill content (for context on what the skill does):
<skill_content>
{skill_content}
</skill_content>

Based on the failures, write a new and improved description that is more likely to trigger correctly. When I say "based on the failures", it's a bit of a tricky line to walk because we don't want to overfit to the specific cases you're seeing. So what I DON'T want you to do is produce an ever-expanding list of specific queries that this skill should or shouldn't trigger for. Instead, try to generalize from the failures to broader categories of user intent and situations where the skill would be useful or not useful. The reason for this is twofold:

1. Avoid overfitting
2. The list might get loooong and it's injected into ALL queries and there might be a lot of skills, so we don't want to blow too much space on any given description.

Concretely, your description should not be more than about 100-200 words, even if that comes at the cost of accuracy. There is a hard limit of 1024 characters — descriptions over that will be truncated, so stay comfortably under it.

Here are some tips that we've found to work well in writing these descriptions:
- The skill should be phrased in the imperative -- "Use this skill for" rather than "this skill does"
- The skill description should focus on the user's intent, what they are trying to achieve, vs. the implementation details of how the skill works.
- The description competes with other skills for Claude's attention — make it distinctive and immediately recognizable.
- If you're getting lots of failures after repeated attempts, change things up. Try different sentence structures or wordings.

I'd encourage you to be creative and mix up the style in different iterations since you'll have multiple opportunities to try different approaches and we'll just grab the highest-scoring one at the end. 

Please respond with only the new description text in <new_description> tags, nothing else."""


def _format_failure_section(title: str, results: list[dict]) -> str:
    if not results:
        return ""
    lines = [f"{title}:\n"]
    for result in results:
        lines.append(
            f'  - "{result["query"]}" '
            f"(triggered {result['triggers']}/{result['runs']} times)\n"
        )
    lines.append("\n")
    return "".join(lines)


def _format_history(history: list[dict]) -> str:
    if not history:
        return ""
    lines = [
        "PREVIOUS ATTEMPTS (do NOT repeat these — try something structurally different):\n\n"
    ]
    for attempt in history:
        train_score = (
            f"{attempt.get('train_passed', attempt.get('passed', 0))}/"
            f"{attempt.get('train_total', attempt.get('total', 0))}"
        )
        test_score = (
            f"{attempt.get('test_passed', '?')}/{attempt.get('test_total', '?')}"
            if attempt.get("test_passed") is not None
            else None
        )
        score = f"train={train_score}" + (f", test={test_score}" if test_score else "")
        lines.append(f"<attempt {score}>\n")
        lines.append(f'Description: "{attempt["description"]}"\n')
        if "results" in attempt:
            lines.append("Train results:\n")
            for result in attempt["results"]:
                status = "PASS" if result["pass"] else "FAIL"
                lines.append(
                    f'  [{status}] "{result["query"][:80]}" '
                    f"(triggered {result['triggers']}/{result['runs']})\n"
                )
        if attempt.get("note"):
            lines.append(f"Note: {attempt['note']}\n")
        lines.append("</attempt>\n\n")
    return "".join(lines)


def _build_prompt(
    skill_name: str,
    skill_content: str,
    current_description: str,
    eval_results: dict,
    history: list[dict],
    test_results: dict | None,
) -> str:
    train_summary = eval_results["summary"]
    train_score = f"{train_summary['passed']}/{train_summary['total']}"
    if test_results:
        test_summary = test_results["summary"]
        scores = f"Train: {train_score}, Test: {test_summary['passed']}/{test_summary['total']}"
    else:
        scores = f"Train: {train_score}"

    failed_triggers = [
        result
        for result in eval_results["results"]
        if result["should_trigger"] and not result["pass"]
    ]
    false_triggers = [
        result
        for result in eval_results["results"]
        if not result["should_trigger"] and not result["pass"]
    ]
    return "".join(
        (
            _PROMPT_HEADER.format(
                skill_name=skill_name,
                current_description=current_description,
                scores_summary=scores,
            ),
            _format_failure_section(
                "FAILED TO TRIGGER (should have triggered but didn't)", failed_triggers
            ),
            _format_failure_section(
                "FALSE TRIGGERS (triggered but shouldn't have)", false_triggers
            ),
            _format_history(history),
            _PROMPT_FOOTER.format(skill_content=skill_content),
        )
    )


def _extract_description(response: str) -> str:
    match = re.search(r"<new_description>(.*?)</new_description>", response, re.DOTALL)
    return match.group(1).strip().strip('"') if match else response.strip().strip('"')


def _shorten_overlong_description(
    prompt: str, description: str, model: str, transcript: dict
) -> str:
    shorten_prompt = (
        f"{prompt}\n\n"
        f"---\n\n"
        f"A previous attempt produced this description, which at "
        f"{len(description)} characters is over the 1024-character hard limit:\n\n"
        f'"{description}"\n\n'
        f"Rewrite it to be under 1024 characters while keeping the most "
        f"important trigger words and intent coverage. Respond with only "
        f"the new description in <new_description> tags."
    )
    response = _call_claude(shorten_prompt, model)
    shortened = _extract_description(response)
    transcript.update(
        {
            "rewrite_prompt": shorten_prompt,
            "rewrite_response": response,
            "rewrite_description": shortened,
            "rewrite_char_count": len(shortened),
        }
    )
    return shortened


def _write_transcript(log_dir: Path, iteration: int | None, transcript: dict) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"improve_iter_{iteration or 'unknown'}.json"
    log_file.write_text(json.dumps(transcript, indent=2), encoding="utf-8")


def improve_description(
    skill_name: str,
    skill_content: str,
    current_description: str,
    eval_results: dict,
    history: list[dict],
    model: str,
    test_results: dict | None = None,
    log_dir: Path | None = None,
    iteration: int | None = None,
) -> str:
    """Ask Claude for a better description and record the response."""
    prompt = _build_prompt(
        skill_name,
        skill_content,
        current_description,
        eval_results,
        history,
        test_results,
    )
    response = _call_claude(prompt, model)
    description = _extract_description(response)
    transcript = {
        "iteration": iteration,
        "prompt": prompt,
        "response": response,
        "parsed_description": description,
        "char_count": len(description),
        "over_limit": len(description) > 1024,
    }
    if len(description) > 1024:
        description = _shorten_overlong_description(
            prompt, description, model, transcript
        )
    transcript["final_description"] = description
    if log_dir:
        _write_transcript(log_dir, iteration, transcript)
    return description


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Improve a skill description based on eval results"
    )
    parser.add_argument(
        "--eval-results",
        required=True,
        help="Path to eval results JSON (from run_eval.py)",
    )
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument(
        "--history", default=None, help="Path to history JSON (previous attempts)"
    )
    parser.add_argument("--model", required=True, help="Model for improvement")
    parser.add_argument(
        "--verbose", action="store_true", help="Print thinking to stderr"
    )
    return parser


def _load_improvement_inputs(
    args: argparse.Namespace,
) -> tuple[str, str, dict, list[dict]]:
    skill_path = Path(args.skill_path)
    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_results = json.loads(Path(args.eval_results).read_text())
    history = json.loads(Path(args.history).read_text()) if args.history else []
    name, _, content = parse_skill_md(skill_path)
    return name, content, eval_results, history


def _print_current_score(description: str, eval_results: dict) -> None:
    summary = eval_results["summary"]
    print(f"Current: {description}", file=sys.stderr)
    print(f"Score: {summary['passed']}/{summary['total']}", file=sys.stderr)


def _updated_history(history: list[dict], eval_results: dict) -> list[dict]:
    summary = eval_results["summary"]
    current_attempt = {
        "description": eval_results["description"],
        "passed": summary["passed"],
        "failed": summary["failed"],
        "total": summary["total"],
        "results": eval_results["results"],
    }
    return history + [current_attempt]


def main() -> None:
    args = _build_argument_parser().parse_args()
    name, content, eval_results, history = _load_improvement_inputs(args)
    current_description = eval_results["description"]
    if args.verbose:
        _print_current_score(current_description, eval_results)

    new_description = improve_description(
        skill_name=name,
        skill_content=content,
        current_description=current_description,
        eval_results=eval_results,
        history=history,
        model=args.model,
    )
    if args.verbose:
        print(f"Improved: {new_description}", file=sys.stderr)

    output = {
        "description": new_description,
        "history": _updated_history(history, eval_results),
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
