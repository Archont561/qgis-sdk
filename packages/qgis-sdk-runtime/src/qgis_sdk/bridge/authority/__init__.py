"""Host-minted file references and per-view grants (decision-20).

The bridge never accepts a path from a page. File authority comes from the
host: a native picker the user answered, or a plugin granting a path it owns.
Either way the host mints a :class:`FileRef` - an opaque id plus display
fields - and keeps the path, the allowed operations and the caller it was minted
for on its own side. Every use goes through :meth:`HostAuthority.resolve_file`,
which checks the ref against the *calling* binding: the view it was minted for,
the generation it was minted in, the operation asked for, and whether the path
still is the file that was granted.

Refusals are typed so a view can act on them (``unknown_handle``: not yours or
never existed, said the same way; ``stale_handle``: was yours, is not any more;
``grant_refused``: yours, but not for that). None of them carries the path.

Network authority follows the same shape: the host grants a view a
:class:`~qgis_sdk.network.NetworkGrant` and the bridge's network operation goes
through it.

Blob authority is the third: a payload above the inline cap (decision-59) is
kept here as bytes the host produced, and the view gets a
:class:`~qgis_sdk.models.BlobRef` it exchanges for bounded chunks. No path is
involved - a blob is never a file - and the bytes are dropped when the view is
released, so a page cannot keep a copy of the host's memory alive by holding an
id. Nothing here imports Qt.

The three kinds are kept by three collaborators - :class:`~._files._FileGrants`,
:class:`~._blobs._BlobGrants` and :class:`~._networks._NetworkGrants` - over the
same table shape, and :class:`HostAuthority` is the one object a host calls.
"""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qgis_sdk.bridge.dispatch import ViewBinding
from qgis_sdk.models.blobs import BlobRef
from qgis_sdk.models.files import FILE_REF, FileRef
from qgis_sdk.network.grants import NetworkGrant

from ._blobs import (
    BLOB_TTL_SECONDS,
    MAX_BLOB_BYTES,
    MAX_BLOBS_PER_VIEW,
    _BlobGrants,
)
from ._files import (
    _DEFAULT_FILE_POLICY,
    DEFAULT_EXPORT_BYTES,
    FILE_SOURCES,
    MAX_FILE_REFS_PER_VIEW,
    FilePolicy,
    _FileGrants,
)
from ._grants import FileOperation
from ._networks import _NetworkGrants

__all__ = [
    "BLOB_TTL_SECONDS",
    "DEFAULT_EXPORT_BYTES",
    "FILE_REF",
    "FILE_SOURCES",
    "MAX_BLOBS_PER_VIEW",
    "MAX_BLOB_BYTES",
    "MAX_FILE_REFS_PER_VIEW",
    "FileOperation",
    "FilePolicy",
    "FileRef",
    "HostAuthority",
]


@dataclass
class HostAuthority:
    """Mint, resolve and revoke the refs and grants of every view of one host.

    One instance per dispatcher: the generation in a binding is the
    dispatcher's, and a ref minted in a replaced generation is stale even if
    the same view id comes back. Each kind of grant has its own record - files,
    blobs, network - and this object is where a host reaches all three.
    """

    clock: Callable[[], float] = time.monotonic
    token: Callable[[], str] = field(default=lambda: secrets.token_hex(16))
    _files: _FileGrants = field(init=False, repr=False)
    _blobs: _BlobGrants = field(init=False, repr=False)
    _networks: _NetworkGrants = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._files = _FileGrants(self.clock, self.token)
        self._blobs = _BlobGrants(self.clock, self.token)
        self._networks = _NetworkGrants()

    def grant_file(
        self,
        binding: ViewBinding,
        path: str | os.PathLike[str],
        policy: FilePolicy = _DEFAULT_FILE_POLICY,
    ) -> FileRef:
        """Mint a ref for ``path`` that only ``binding``'s view can use.

        ``policy`` is what the grant allows and for how long: ``source`` records
        where the authority came from (``picker`` or ``plugin``), a read grant
        needs an existing regular file, and a write grant needs an existing
        parent directory and, to replace an existing file, ``overwrite=True`` -
        a save dialog that confirmed the overwrite is the usual reason to pass
        it. The path is canonicalised once, and the ref names that canonical
        file from now on.
        """
        return self._files.mint(binding, path, policy)

    def grant_directory(
        self,
        binding: ViewBinding,
        path: str | os.PathLike[str],
        *,
        source: str = "plugin",
        ttl_seconds: float | None = None,
    ) -> FileRef:
        """Mint a read ref for an existing directory that only ``binding`` can use.

        What ``DirectoryInput()`` hands a handler: the directory is resolved
        once, and the ref goes stale when the directory is replaced or removed.
        """
        return self._files.mint_directory(
            binding, path, source=source, ttl_seconds=ttl_seconds
        )

    def resolve_file(
        self, binding: ViewBinding, raw: Any, operation: FileOperation
    ) -> Path:
        """Return the canonical path behind ``raw`` for ``operation``, or refuse."""
        return self._files.resolve(binding, raw, operation)

    def export_file(self, binding: ViewBinding, raw: Any, content: str | bytes) -> int:
        """Write ``content`` to the file a write ref names; return the byte count."""
        return self._files.export(binding, raw, content)

    def refs(self, binding: ViewBinding) -> tuple[FileRef, ...]:
        """The live refs of ``binding``'s view in its generation, oldest first."""
        return self._files.refs(binding)

    def revoke(self, ref_id: str) -> bool:
        """Withdraw one ref; the view is told ``stale_handle`` from now on."""
        return self._files.revoke(ref_id)

    def release_view(self, binding: ViewBinding) -> int:
        """Forget everything minted for ``binding``'s view; files are untouched.

        Returns how many file refs were dropped. Revocation tombstones go too:
        a view that was released starts over, and its old ids are unknown.
        """
        dropped = self._files.release_view(binding)
        self._blobs.release_view(binding)
        self._networks.release_view(binding.view_id)
        return dropped

    def prune(self, generation: int) -> int:
        """Drop refs and grants from generations before ``generation``."""
        dropped = self._files.prune(generation)
        self._blobs.prune(generation)
        self._networks.prune(generation)
        return dropped

    def mint_blob(
        self,
        binding: ViewBinding,
        data: bytes | bytearray | memoryview,
        *,
        media_type: str = "application/octet-stream",
        ttl_seconds: float | None = BLOB_TTL_SECONDS,
    ) -> BlobRef:
        """Keep ``data`` for ``binding``'s view and return the ref that names it."""
        return self._blobs.mint(
            binding, data, media_type=media_type, ttl_seconds=ttl_seconds
        )

    def inline_or_blob(
        self,
        binding: ViewBinding,
        data: bytes | bytearray | memoryview,
        *,
        media_type: str = "application/octet-stream",
        cap: int = 256 * 1024,
    ) -> dict[str, Any]:
        """Return a payload inline when it fits ``cap``, and as a blob when it does not."""
        return self._blobs.inline_or_blob(binding, data, media_type=media_type, cap=cap)

    def read_blob(
        self,
        binding: ViewBinding,
        raw: Any,
        *,
        offset: int = 0,
        length: int | None = None,
    ) -> bytes:
        """Return ``length`` bytes of ``raw`` from ``offset``, or refuse."""
        return self._blobs.read(binding, raw, offset=offset, length=length)

    def blob_size(self, binding: ViewBinding, raw: Any) -> int:
        """Return the size of ``raw`` without reading it."""
        return self._blobs.size(binding, raw)

    def blob_info(self, binding: ViewBinding, raw: Any) -> BlobRef:
        """Return the stored ref (size, media type, checksum) without the bytes."""
        return self._blobs.info(binding, raw)

    def grant_network(self, binding: ViewBinding, grant: NetworkGrant) -> None:
        """Give ``binding``'s view ``grant``, replacing any earlier one."""
        self._networks.grant(binding, grant)

    def network_grant(self, binding: ViewBinding) -> NetworkGrant | None:
        """The view's grant in this generation, or ``None``."""
        return self._networks.get(binding)

    def require_network(self, binding: ViewBinding) -> NetworkGrant:
        """The view's grant, or the refusal a network operation reports."""
        return self._networks.require(binding)

    def revoke_network(self, binding: ViewBinding) -> bool:
        """Withdraw the view's network grant."""
        return self._networks.revoke(binding)
