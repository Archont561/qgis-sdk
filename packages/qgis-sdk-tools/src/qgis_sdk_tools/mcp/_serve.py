"""Serving the commands over stdio until the client disconnects.

Each operation runs the actual CLI in a subprocess: command output is captured
and cannot contaminate the MCP protocol on stdout. This is not a sandbox.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ._process import DevSession, run, spawn
from ._types import _COMMANDS, CommandResult, DevInfo, StartedDevInfo, tool_names

__all__ = ["serve"]


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_serve_p1(_s):
    _s.sessions: dict[str, DevSession] = {}
    _s.session_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield None
        finally:
            await asyncio.gather(*(session.stop() for session in _s.sessions.values()))

    _s.lifespan = lifespan


def _cc_serve_p2(_s):

    _s.server = MCPServer(
        "qgis-sdk",
        lifespan=_s.lifespan,
        instructions=(
            "These tools run local CLI commands with the user's full permissions. "
            "The working directory is not a sandbox; commands can read or modify any "
            "accessible file and execute project code. Ask the user before side effects. "
            "Pass arguments as separate strings exactly as on the qgis-sdk command line; "
            "use --help for options. No interactive input is available."
        ),
    )


def _cc_serve_p3(_s):

    def register(name: str, command: str, description: str) -> None:
        async def invoke(args: list[str]) -> CommandResult:
            return await run(_s.root, command, args)

        _s.invoke = invoke

        _s.server.add_tool(
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

    _s.register = register


def _cc_serve_p4(_s):

    _s.offered = set(tool_names())
    for name, (command, description) in _COMMANDS.items():
        _s.name = name
        _s.command = command
        _s.description = description
        if _s.name in _s.offered:
            _s.register(_s.name, _s.command, _s.description)


def _cc_serve_p5(_s):

    @_s.server.tool(
        structured_output=True,
        name="qgis_sdk_dev",
        description="Start qgis-sdk dev in the background (launches QGIS and possibly a web server). Returns a session ID; poll with qgis_sdk_dev_status and stop with qgis_sdk_dev_stop. Arguments are CLI strings; no interactive input.",
    )
    async def dev(args: list[str]) -> StartedDevInfo:
        async with _s.session_lock:
            if len(_s.sessions) >= 8:
                raise ValueError("Too many dev sessions; stop one first")
            process = await spawn(_s.root, "dev", args)
            session_id = uuid4().hex
            _s.sessions[session_id] = DevSession(process)
            return {"session_id": session_id, **_s.sessions[session_id].report()}

    _s.dev = dev


def _cc_serve_p6(_s):

    @_s.server.tool(
        structured_output=True,
        name="qgis_sdk_dev_status",
        description="Read bounded recent output and exit status for a dev session.",
    )
    async def dev_status(session_id: str) -> DevInfo:
        if session_id not in _s.sessions:
            raise ValueError("Unknown dev session")
        return _s.sessions[session_id].report()

    _s.dev_status = dev_status


def _cc_serve_p7(_s):

    @_s.server.tool(
        name="qgis_sdk_dev_stop",
        description="Stop and forget a dev session.",
        structured_output=True,
    )
    async def dev_stop(session_id: str) -> DevInfo:
        if session_id not in _s.sessions:
            raise ValueError("Unknown dev session")
        session = _s.sessions.pop(session_id)
        await session.stop()
        return session.report()

    _s.dev_stop = dev_stop


def _cc_serve_p8(_s):

    _s.server.run(transport="stdio")


def serve(root: Path) -> None:
    """Serve the commands until the stdio client disconnects."""
    _s = _CcState(root=root)
    for _p in (
        _cc_serve_p1,
        _cc_serve_p2,
        _cc_serve_p3,
        _cc_serve_p4,
        _cc_serve_p5,
        _cc_serve_p6,
        _cc_serve_p7,
        _cc_serve_p8,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None
