"""Running CLI commands in subprocesses and draining their output.

One rule governs both one-shot commands and live dev sessions: the tail is
what diagnoses a failure - a traceback, a failing summary - so output is kept
to the newest bytes up to the limit.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

from ._types import _LIMIT, _TIMEOUT, CommandResult, DevInfo

__all__: list[str] = []


def _keep_tail(output: bytearray, data: bytes, truncated: list[bool]) -> None:
    """Append stream data, keeping the newest bytes up to the limit.

    The tail is what diagnoses a failure - a traceback, a failing summary - so
    one rule governs both one-shot commands and live dev sessions.
    """
    output.extend(data)
    if len(output) > _LIMIT:
        del output[:-_LIMIT]
        truncated[0] = True


async def _capture(
    stream: asyncio.StreamReader, output: bytearray, truncated: list[bool]
) -> None:
    while data := await stream.read(65536):
        _keep_tail(output, data, truncated)


async def _finish_readers(tasks: list[asyncio.Task], truncated: list[bool]) -> None:
    # Descendants can inherit a pipe after the CLI exits. Never wait on them
    # indefinitely, including when stopping a dev session.
    _, pending = await asyncio.wait(tasks, timeout=2)
    if pending:
        truncated[0] = True
        for task in pending:
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def _spawn_options() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


async def _stop(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), 5)
    except TimeoutError:
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), 2)
        except TimeoutError:
            # A descendant may still hold inherited pipes, especially on Windows.
            pass


async def spawn(
    root: Path, command: str, args: list[str]
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "qgis_sdk_tools",
        *command.split(),
        *args,
        cwd=root,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **_spawn_options(),
    )


async def run(root: Path, command: str, args: list[str]) -> CommandResult:
    process = await spawn(root, command, args)
    assert process.stdout is not None and process.stderr is not None
    stdout = bytearray()
    stderr = bytearray()
    truncated = [False]
    readers = [
        asyncio.create_task(_capture(process.stdout, stdout, truncated)),
        asyncio.create_task(_capture(process.stderr, stderr, truncated)),
    ]
    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), _TIMEOUT)
    except TimeoutError:
        timed_out = True
        await _stop(process)
    except BaseException:
        await _stop(process)
        await _finish_readers(readers, truncated)
        raise
    await _finish_readers(readers, truncated)
    return {
        "exit_code": process.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "truncated": truncated[0],
        "timed_out": timed_out,
    }


class DevSession:
    def __init__(self, process: asyncio.subprocess.Process):
        self.process = process
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.truncated = [False]
        assert process.stdout is not None and process.stderr is not None
        self.tasks = [
            asyncio.create_task(self._drain(process.stdout, self.stdout)),
            asyncio.create_task(self._drain(process.stderr, self.stderr)),
        ]

    async def _drain(self, stream: asyncio.StreamReader, output: bytearray) -> None:
        while data := await stream.read(65536):
            _keep_tail(output, data, self.truncated)

    def report(self) -> DevInfo:
        return {
            "running": self.process.returncode is None,
            "exit_code": self.process.returncode,
            "stdout": self.stdout.decode("utf-8", errors="replace"),
            "stderr": self.stderr.decode("utf-8", errors="replace"),
            "truncated": self.truncated[0],
        }

    async def stop(self) -> None:
        await _stop(self.process)
        await _finish_readers(self.tasks, self.truncated)
