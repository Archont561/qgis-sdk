"""PyQGIS-backed settings, scoped to one plugin runtime.

``QgsSettings`` is global to the QGIS profile, so the adapter keeps two things
explicit: every key is written under a caller-supplied prefix, and no operation
survives the owner scope closing. Pure code never reaches ``QgsSettings`` itself;
it receives this adapter through the ``Settings`` contract.
"""

from __future__ import annotations

from qgis.core import QgsSettings

from qgis_sdk.core import ResourceScope

__all__ = ["NativeSettings"]


class NativeSettings:
    """Read and write string settings under one prefix of the QGIS profile."""

    def __init__(
        self,
        scope: ResourceScope,
        prefix: str,
        settings: QgsSettings | None = None,
    ) -> None:
        self._scope = scope
        self._prefix = prefix.strip("/")
        if not self._prefix:
            raise ValueError("A settings prefix is required to scope storage")
        self._settings = settings if settings is not None else QgsSettings()

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the stored value, the default, or ``None`` when absent."""
        self._scope.ensure_open()
        stored = self._settings.value(self._key(key), None)
        return default if stored is None else str(stored)

    def set(self, key: str, value: str) -> None:
        """Store a value under this runtime's prefix."""
        self._scope.ensure_open()
        self._settings.setValue(self._key(key), value)

    def _key(self, key: str) -> str:
        return f"{self._prefix}/{key.lstrip('/')}"
