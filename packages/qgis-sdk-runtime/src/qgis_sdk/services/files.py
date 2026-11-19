"""File authority for plugin code: mint a ``FileRef``, resolve one to a path.

A handler that declared ``source: FileInput()`` receives a :class:`FileRef`,
never a path (decision-20). This is the one door from a ref back to the
filesystem, and the one place a form component mints a ref from a picker's
result, so a page, a toolbox run and a native form all hand a handler refs
that one host authority resolves.
"""

from __future__ import annotations

from collections.abc import Iterable
from os import PathLike
from pathlib import Path
from typing import Any, Protocol

from qgis_sdk.models.files import FileRef


class Files(Protocol):
    """Mint and resolve file refs on behalf of this plugin."""

    def grant_file(
        self,
        path: str | PathLike[str],
        *,
        operations: Iterable[str] = ("read",),
        overwrite: bool = False,
    ) -> FileRef:
        """Mint a ref for one file: read needs it to exist, write its parent.

        Args:
            path: The file the ref stands for.
            operations: What the ref may be used for: ``read``, ``write``,
                ``create`` or ``delete``.
            overwrite: Whether a write may replace an existing file.
        """
        ...

    def grant_directory(self, path: str | PathLike[str]) -> FileRef:
        """Mint a read ref for an existing directory.

        Args:
            path: The directory the ref stands for.
        """
        ...

    def resolve(self, ref: FileRef | Any, *, operation: str = "read") -> Path:
        """Return the canonical path behind ``ref`` for ``operation``, or refuse.

        Args:
            ref: The ref a service was handed.
            operation: What the caller intends to do with the path.
        """
        ...
