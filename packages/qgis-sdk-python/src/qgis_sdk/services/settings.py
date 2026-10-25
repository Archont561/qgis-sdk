"""Scoped settings access; never a global ``QSettings`` instance."""

from __future__ import annotations

from typing import Protocol


class Settings(Protocol):
    """Read and write string values owned by one plugin runtime.

    Pure code reaches settings only through this injected contract, so the
    QGIS-free layers stay importable and testable without Qt. Values are strings
    because that is what the host persists; typing is the caller's schema.
    """

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the stored value, the default, or ``None`` when absent."""
        ...

    def set(self, key: str, value: str) -> None:
        """Store a value under this runtime's key scope."""
        ...
