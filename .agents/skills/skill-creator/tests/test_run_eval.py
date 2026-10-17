from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any, Self

import pytest

from scripts import run_eval as run_eval_script


class DeferredFuture:
    def __init__(self, function: Callable[..., bool], args: tuple[Any, ...]) -> None:
        self._function = function
        self._args = args

    def result(self) -> bool:
        return self._function(*self._args)


class InlineExecutor:
    def __init__(self, max_workers: int) -> None:
        self.max_workers = max_workers

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def submit(self, function: Callable[..., bool], *args: Any) -> DeferredFuture:
        return DeferredFuture(function, args)


def _patch_inline_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_eval_script, "ProcessPoolExecutor", InlineExecutor)
    monkeypatch.setattr(run_eval_script, "as_completed", lambda futures: futures)


def _run_eval(eval_set: list[dict[str, Any]]) -> dict[str, Any]:
    return run_eval_script.run_eval(
        eval_set=eval_set,
        skill_name="demo",
        description="Use this skill for demonstrations.",
        num_workers=1,
        timeout=1,
        project_root=Path("."),
    )


def test_failed_worker_is_not_scored_as_a_negative_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_inline_executor(monkeypatch)

    def failed_worker(*_: object) -> bool:
        raise RuntimeError("Claude CLI failed")

    monkeypatch.setattr(run_eval_script, "run_single_query", failed_worker)

    with pytest.raises(RuntimeError, match="Claude CLI failed"):
        _run_eval([{"query": "irrelevant", "should_trigger": False}])


def test_successful_non_trigger_remains_a_valid_negative_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_inline_executor(monkeypatch)
    monkeypatch.setattr(run_eval_script, "run_single_query", lambda *_: False)

    output = _run_eval([{"query": "irrelevant", "should_trigger": False}])

    assert output["summary"] == {"total": 1, "passed": 1, "failed": 0}
    assert output["results"] == [
        {
            "query": "irrelevant",
            "should_trigger": False,
            "trigger_rate": 0.0,
            "triggers": 0,
            "runs": 1,
            "pass": True,
        }
    ]


class FakeProcess:
    def __init__(self, returncode: int | None) -> None:
        self.stdout = BytesIO()
        self.returncode = returncode

    def poll(self) -> int | None:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9

    def wait(self) -> int:
        self.returncode = self.returncode or 0
        return self.returncode


def test_query_timeout_is_reported_as_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        run_eval_script.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess(None)
    )
    project_root = tmp_path / "project"

    with pytest.raises(TimeoutError, match="timed out"):
        run_eval_script.run_single_query(
            query="query",
            skill_name="demo",
            skill_description="A demo skill.",
            timeout=0,
            project_root=str(project_root),
        )

    assert not list((project_root / ".claude" / "commands").glob("*.md"))


def test_nonzero_cli_exit_is_reported_as_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        run_eval_script.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess(1)
    )
    project_root = tmp_path / "project"

    with pytest.raises(run_eval_script.subprocess.CalledProcessError):
        run_eval_script.run_single_query(
            query="query",
            skill_name="demo",
            skill_description="A demo skill.",
            timeout=1,
            project_root=str(project_root),
        )

    assert not list((project_root / ".claude" / "commands").glob("*.md"))


class StreamingProcess:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._read_fd, write_fd = os.pipe()
        self.stdout = os.fdopen(self._read_fd, "rb", buffering=0)
        self.returncode: int | None = None
        self._poll_count = 0
        payload = "\n".join(json.dumps(event) for event in events).encode("utf-8")
        os.write(write_fd, payload)
        os.close(write_fd)

    def poll(self) -> int | None:
        self._poll_count += 1
        if self._poll_count == 1:
            return None
        self.returncode = 0
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9

    def wait(self) -> int:
        self.returncode = self.returncode or 0
        return self.returncode


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "run_eval streams with select() on the CLI stdout pipe; Windows select() "
        "only accepts sockets, so this path is POSIX-only"
    ),
)
def test_streamed_skill_call_is_detected_even_without_a_trailing_newline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "project"

    def create_process(
        _command: list[str], *, cwd: str, **_: object
    ) -> StreamingProcess:
        command_file = next((Path(cwd) / ".claude" / "commands").glob("*.md"))
        return StreamingProcess(
            [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Skill",
                                "input": {"skill": command_file.stem},
                            }
                        ]
                    },
                }
            ]
        )

    monkeypatch.setattr(run_eval_script.subprocess, "Popen", create_process)

    triggered = run_eval_script.run_single_query(
        query="query",
        skill_name="demo",
        skill_description="A demo skill.",
        timeout=1,
        project_root=str(project_root),
    )

    assert triggered is True
    assert not list((project_root / ".claude" / "commands").glob("*.md"))
