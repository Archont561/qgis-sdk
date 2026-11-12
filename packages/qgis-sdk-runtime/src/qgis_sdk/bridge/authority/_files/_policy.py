"""What one file grant allows: its operations, origin, lifetime and ceiling."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from qgis_sdk.bridge.authority._grants import FileGrant, FileOperation
from qgis_sdk.bridge.dispatch import ViewBinding
from qgis_sdk.models import QgisSdkBridgeError
from qgis_sdk.models.files import FileRef

__all__ = [
    "DEFAULT_EXPORT_BYTES",
    "FILE_SOURCES",
    "MAX_FILE_REFS_PER_VIEW",
    "FilePolicy",
]

MAX_FILE_REFS_PER_VIEW = 64
"""Refs one view may hold at once; a picker loop cannot grow the table unbounded."""

DEFAULT_EXPORT_BYTES = 4 * 1024 * 1024
"""Default ceiling for one export: the content crosses the channel as a string."""

FILE_SOURCES = frozenset({"picker", "plugin"})
"""Where file authority comes from: a picker the user answered, or the plugin itself."""


@dataclass(frozen=True)
class _Target:
    """What a grant names once the path is settled: the ref, its path, its identity."""

    ref: FileRef
    path: Path
    identity: tuple[int, int] | None
    expires_at: float | None


@dataclass(frozen=True)
class FilePolicy:
    """What one grant allows: its operations, origin, lifetime and ceiling.

    The five knobs travel together because they are read together - a grant is
    checked for what it allows and when it stops allowing it - so this is both
    what ``HostAuthority.grant_file`` takes and what the grant machinery reads.
    The default is the ordinary one: read one existing file, no expiry, the
    export ceiling.
    """

    operations: Iterable[str | FileOperation] = (FileOperation.READ,)
    overwrite: bool = False
    source: str = "plugin"
    ttl_seconds: float | None = None
    max_bytes: int = DEFAULT_EXPORT_BYTES

    def allowed(self) -> frozenset[FileOperation]:
        """The operations this policy grants, refusing anything but read or write."""
        return _operations_of(self.operations)

    def expiry(self, clock: Callable[[], float]) -> float | None:
        """When this grant stops working, or ``None`` for one that never expires."""
        return None if self.ttl_seconds is None else clock() + self.ttl_seconds

    def grant(self, binding: ViewBinding, target: _Target) -> FileGrant:
        """The host's side of ``target``, spelled as this policy declares it."""
        return FileGrant(
            ref=target.ref,
            view_id=binding.view_id,
            generation=binding.generation,
            path=target.path,
            operations=self.allowed(),
            overwrite=bool(self.overwrite),
            source=self.source,
            max_bytes=int(self.max_bytes),
            identity=target.identity,
            expires_at=target.expires_at,
        )


#: The ordinary grant, shared because a policy is immutable: one existing file,
#: read, no expiry, the export ceiling. ``grant_file`` takes it as its default.
_DEFAULT_FILE_POLICY = FilePolicy()


def _operations_of(
    operations: Iterable[str | FileOperation],
) -> frozenset[FileOperation]:
    """The operations a grant allows, refusing anything that is not read or write."""
    try:
        allowed = frozenset(FileOperation(op) for op in operations)
    except ValueError as error:
        raise QgisSdkBridgeError(
            f"a file grant allows read and/or write, not {error}"
        ) from None
    if not allowed:
        raise QgisSdkBridgeError("a file grant allows at least one operation")
    return allowed


def refuse_source(source: str) -> None:
    """Refuse a grant whose origin is neither a picker nor the plugin itself."""
    if source not in FILE_SOURCES:
        raise QgisSdkBridgeError(
            f"{source!r} is not a file grant source; use picker or plugin"
        )


def refuse_too_many(binding: ViewBinding, held: int) -> None:
    """Refuse the ref past the per-view ceiling."""
    if held >= MAX_FILE_REFS_PER_VIEW:
        raise QgisSdkBridgeError(
            f"view {binding.view_id!r} already holds {MAX_FILE_REFS_PER_VIEW} "
            "file refs; release some before granting more"
        )
