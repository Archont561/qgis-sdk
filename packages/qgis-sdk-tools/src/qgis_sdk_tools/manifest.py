"""One reading of ``pyproject.toml`` for every command.

``check``, ``build``, ``dev`` and the project loader all open the same file
and walk the same ``[tool.qgis-sdk.*]`` tables. They decide differently what
a missing or malformed manifest means - a diagnostic, a silent skip, a
refusal - so this module settles only the part they agree on: how the file
is read and how a nested table is reached. It imports nothing of the
package so any module may use it without a cycle.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

__all__ = ["read_pyproject", "table"]


def read_pyproject(path: Path) -> tuple[dict[str, object] | None, str | None]:
    """Parse the manifest at ``path`` once.

    Returns ``(data, None)`` when it parses, ``(None, None)`` when there is no
    file, and ``(None, reason)`` when the text is not TOML; ``reason`` is the
    parser's own message so a diagnostic can quote it. Reading errors other
    than absence propagate: a manifest that exists but cannot be read is the
    caller's to explain.
    """
    path = Path(path)
    if not path.is_file():
        return None, None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8")), None
    except tomllib.TOMLDecodeError as error:
        return None, str(error)


def table(data: object, *keys: str) -> dict[str, object] | None:
    """The table at ``keys`` inside ``data``, or ``None`` when any step is not one."""
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data if isinstance(data, dict) else None
