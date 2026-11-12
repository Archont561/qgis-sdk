"""The result shapes and command table of the MCP adapter.

Each operation runs the actual CLI in a subprocess: command output is captured
and cannot contaminate the MCP protocol on stdout. This is not a sandbox.
"""

from __future__ import annotations

from typing_extensions import TypedDict

__all__ = [
    "DEVELOPER_ONLY",
    "CommandResult",
    "DevInfo",
    "StartedDevInfo",
    "tool_names",
]


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
