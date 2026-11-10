"""The grant records each kind of authority keeps, and the table that holds them."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

from qgis_sdk.models.blobs import BlobRef
from qgis_sdk.models.files import FileRef
from qgis_sdk.network.grants import NetworkGrant


class FileOperation(str, Enum):
    """What a file grant allows; a grant lists one or both."""

    READ = "read"
    WRITE = "write"


class _Grant(Protocol):
    """What the table needs of any grant: who holds it, from when, and until when."""

    view_id: str
    generation: int
    expires_at: float | None


@dataclass(slots=True)
class _FileGrant:
    """The host's side of a ref; never serialised, never shown."""

    ref: FileRef
    view_id: str
    generation: int
    path: Path
    operations: frozenset[FileOperation]
    overwrite: bool
    source: str
    max_bytes: int
    identity: tuple[int, int] | None
    expires_at: float | None


@dataclass(slots=True)
class _BlobGrant:
    """The host's side of one blob: the bytes, and who may ask for them."""

    ref: BlobRef
    view_id: str
    generation: int
    data: bytes
    expires_at: float | None


@dataclass(slots=True)
class _NetworkGrant:
    """One view's network grant, and the generation it was given in."""

    grant: NetworkGrant
    generation: int


@dataclass
class _Table:
    """The grants of one kind, keyed by the opaque id the host minted for them.

    Ownership, generation and expiry are what every kind of grant is checked
    for, so they are answered here once: a table knows who holds what, and how
    to forget a view or an older generation without the caller walking it.
    """

    clock: Callable[[], float]
    items: dict[str, _Grant] = field(default_factory=dict)

    def add(self, ref_id: str, grant: _Grant) -> None:
        self.items[ref_id] = grant

    def get(self, ref_id: str) -> _Grant | None:
        return self.items.get(ref_id)

    def drop(self, ref_id: str) -> _Grant | None:
        return self.items.pop(ref_id, None)

    def count(self, view_id: str) -> int:
        """How many grants one view holds."""
        return sum(1 for grant in self.items.values() if grant.view_id == view_id)

    def held_by(self, view_id: str) -> list[tuple[str, _Grant]]:
        """The ids and grants one view holds, in the order they were minted."""
        return [
            (ref_id, grant)
            for ref_id, grant in self.items.items()
            if grant.view_id == view_id
        ]

    def drop_expired(self) -> int:
        """Drop every grant past its expiry, whoever holds it; return how many."""
        now = self.clock()
        stale = [
            ref_id
            for ref_id, grant in self.items.items()
            if grant.expires_at is not None and now >= grant.expires_at
        ]
        for ref_id in stale:
            del self.items[ref_id]
        return len(stale)

    def release_view(self, view_id: str) -> int:
        """Forget every grant one view holds; return how many were dropped."""
        held = [ref_id for ref_id, _ in self.held_by(view_id)]
        for ref_id in held:
            del self.items[ref_id]
        return len(held)

    def prune(self, generation: int) -> int:
        """Drop the grants of every generation before ``generation``."""
        stale = [
            ref_id
            for ref_id, grant in self.items.items()
            if grant.generation < generation
        ]
        for ref_id in stale:
            del self.items[ref_id]
        return len(stale)


def _identity(path: Path) -> tuple[int, int] | None:
    """The device and inode that name one file, or ``None`` when it is gone."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino)
