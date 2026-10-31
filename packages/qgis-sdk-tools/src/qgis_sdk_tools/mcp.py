"""Optional stdio MCP adapter for the developer CLI, not the plugin HTTP runtime.

Each operation runs the actual CLI in a subprocess: command output is captured
and cannot contaminate the MCP protocol on stdout. This is not a sandbox.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from typing_extensions import TypedDict


class CommandResult(TypedDict):
    exit_code: int | None
    stdout: str
    stderr: str
    truncated: bool
    timed_out: bool


class DevInfo(TypedDict):
    running: bool
    exit_code: int | None
    stdout: str
    stderr: str
    truncated: bool


class StartedDevInfo(DevInfo):
    session_id: str


_LIMIT = 256 * 1024
_TIMEOUT = 300
_COMMANDS = {
    "new": ("new", "Create plugin files; may overwrite files or install packages."),
    "scaffold": (
        "scaffold",
        "Deprecated alias for new; may write files or install packages.",
    ),
    "bridge_generate": (
        "bridge generate",
        "Generate bridge files from project code; may write files and execute code.",
    ),
    "processing_generate": (
        "processing generate",
        "Generate Processing files from project code; may write files and execute code.",
    ),
    "check": ("check", "Check a plugin project; may import project code."),
    "build": (
        "build",
        "Build a plugin archive; may write files and run project build tools.",
    ),
    "test": ("test", "Run project tests; executes arbitrary project code."),
    "run": (
        "run",
        (
            "Start the project as a standalone app; starts QGIS and blocks until "
            "it quits. Pass --once for a smoke run that stops by itself."
        ),
    ),
    "targets": ("targets", "Report the SDK support matrix and host QGIS."),
    "ui_list": ("ui list", "List the surfaces a plugin declares; starts QGIS."),
    "ui_open": (
        "ui open",
        "Open one surface in the plugin's host and report the window; starts QGIS.",
    ),
    "ui_snapshot": (
        "ui snapshot",
        "Capture one surface as a structured tree plus a PNG; starts QGIS.",
    ),
    "ui_act": (
        "ui act",
        (
            "Drive a surface with synthetic input, then capture it; starts QGIS. "
            "Developer mode only."
        ),
    ),
    "ui_diff": ("ui diff", "Compare two captures; exits 1 on a structural change."),
}

DEVELOPER_ONLY = frozenset({"ui_act"})
"""Tools that act *inside* an open plugin window (decision-51 point 4).

The MCP server is developer tooling - it starts QGIS and drives the plugin's own
surfaces - so it serves them; what a user's install exposes to a client is the
plugin's HTTP description (``GET /plugin``), which lists declared actions and
streams and can name no such tool. Driving a surface exists only here and in
the probe this module can call, never in the runtime a plugin ZIP vendors.
"""


def tool_names(*, developer: bool = True) -> tuple[str, ...]:
    """The tools this adapter offers, in registration order.

    ``developer=False`` is the list a deployment without developer tooling would
    serve: everything that reads - listing, capturing, comparing - stays, and
    the tool that synthesises input into an open window goes (decision-51
    point 4). The stdio server always serves it; a user's install never gets
    this adapter at all, only the plugin's HTTP description.
    """
    return tuple(
        name
        for name in (*_COMMANDS, "dev", "dev_status", "dev_stop")
        if developer or name not in DEVELOPER_ONLY
    )


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


async def _spawn(
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


async def _run(root: Path, command: str, args: list[str]) -> CommandResult:
    process = await _spawn(root, command, args)
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


class _DevSession:
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


def serve(root: Path) -> None:
    """Serve the commands until the stdio client disconnects."""
    sessions: dict[str, _DevSession] = {}
    session_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield None
        finally:
            await asyncio.gather(*(session.stop() for session in sessions.values()))

    server = MCPServer(
        "qgis-sdk",
        lifespan=lifespan,
        instructions=(
            "These tools run local CLI commands with the user's full permissions. "
            "The working directory is not a sandbox; commands can read or modify any "
            "accessible file and execute project code. Ask the user before side effects. "
            "Pass arguments as separate strings exactly as on the qgis-sdk command line; "
            "use --help for options. No interactive input is available."
        ),
    )

    def register(name: str, command: str, description: str) -> None:
        async def invoke(args: list[str]) -> CommandResult:
            return await _run(root, command, args)

        server.add_tool(
            invoke,
            structured_output=True,
            name=f"qgis_sdk_{name}",
            description=f"Run qgis-sdk {command}. {description} Pass CLI arguments as an array of strings. Output is capped and execution times out after 300 seconds.",
            annotations=ToolAnnotations(
                readOnlyHint=name == "targets",
                destructiveHint=name != "targets",
                openWorldHint=True,
            ),
        )

    offered = set(tool_names())
    for name, (command, description) in _COMMANDS.items():
        if name in offered:
            register(name, command, description)

    @server.tool(
        structured_output=True,
        name="qgis_sdk_dev",
        description="Start qgis-sdk dev in the background (launches QGIS and possibly a web server). Returns a session ID; poll with qgis_sdk_dev_status and stop with qgis_sdk_dev_stop. Arguments are CLI strings; no interactive input.",
    )
    async def dev(args: list[str]) -> StartedDevInfo:
        async with session_lock:
            if len(sessions) >= 8:
                raise ValueError("Too many dev sessions; stop one first")
            process = await _spawn(root, "dev", args)
            session_id = uuid4().hex
            sessions[session_id] = _DevSession(process)
            return {"session_id": session_id, **sessions[session_id].report()}

    @server.tool(
        structured_output=True,
        name="qgis_sdk_dev_status",
        description="Read bounded recent output and exit status for a dev session.",
    )
    async def dev_status(session_id: str) -> DevInfo:
        if session_id not in sessions:
            raise ValueError("Unknown dev session")
        return sessions[session_id].report()

    @server.tool(
        name="qgis_sdk_dev_stop",
        description="Stop and forget a dev session.",
        structured_output=True,
    )
    async def dev_stop(session_id: str) -> DevInfo:
        if session_id not in sessions:
            raise ValueError("Unknown dev session")
        session = sessions.pop(session_id)
        await session.stop()
        return session.report()

    server.run(transport="stdio")
