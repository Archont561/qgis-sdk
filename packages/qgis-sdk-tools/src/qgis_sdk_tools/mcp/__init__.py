"""Optional stdio MCP adapter for the developer CLI, not the plugin HTTP runtime.

Each operation runs the actual CLI in a subprocess: command output is captured
and cannot contaminate the MCP protocol on stdout. This is not a sandbox.
"""

from __future__ import annotations

from ._process import _capture as _capture
from ._serve import serve
from ._types import (
    _LIMIT as _LIMIT,
)
from ._types import (
    DEVELOPER_ONLY,
    CommandResult,
    DevInfo,
    StartedDevInfo,
    tool_names,
)

__all__ = [
    "DEVELOPER_ONLY",
    "CommandResult",
    "DevInfo",
    "StartedDevInfo",
    "serve",
    "tool_names",
]
