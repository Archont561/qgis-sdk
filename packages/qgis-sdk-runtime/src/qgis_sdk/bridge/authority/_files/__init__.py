"""File grants: the refs a view was handed, and what each one still allows."""

from __future__ import annotations

from ._grants import FileGrants
from ._policy import (
    _DEFAULT_FILE_POLICY as _DEFAULT_FILE_POLICY,
)
from ._policy import (
    DEFAULT_EXPORT_BYTES,
    FILE_SOURCES,
    MAX_FILE_REFS_PER_VIEW,
    FilePolicy,
)

__all__ = [
    "DEFAULT_EXPORT_BYTES",
    "FILE_SOURCES",
    "MAX_FILE_REFS_PER_VIEW",
    "FileGrants",
    "FilePolicy",
]
