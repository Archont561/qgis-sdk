"""Blob grants: payloads above the inline cap, kept as bytes the view may chunk."""

from __future__ import annotations

import base64
import hashlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Never

from qgis_sdk.bridge.dispatch import ViewBinding
from qgis_sdk.models import (
    QgisSdkBridgeError,
    QgisSdkStaleHandleError,
    QgisSdkUnknownHandleError,
)
from qgis_sdk.models.blobs import BLOB_REF_KIND, BlobRef

from ._grants import BlobGrant, Table

#: How many blobs one view may hold at once. A page that keeps minting them is
#: a page that is not releasing them, and the host's memory is not its to fill.
MAX_BLOBS_PER_VIEW = 16

#: Ceiling for one blob. Above this a producer keeps the bytes where they are
#: and returns a file (decision-59 point 4): a raster or a point cloud never
#: moves whole.
MAX_BLOB_BYTES = 32 * 1024 * 1024

#: How long a blob lives unless the producer asks for something else. Long
#: enough for a client to assemble a payload in chunks, short enough that an
#: abandoned page does not pin megabytes until the view is disposed.
BLOB_TTL_SECONDS = 300.0

DEFAULT_MEDIA_TYPE = "application/octet-stream"
"""What a blob with no declared type is called: bytes, and nothing more."""


@dataclass
class BlobGrants:
    """Keep, describe and hand out the blobs of every view of one host."""

    clock: Callable[[], float]
    token: Callable[[], str]
    table: Table = field(init=False)

    def __post_init__(self) -> None:
        self.table = Table(self.clock)

    def mint(
        self,
        binding: ViewBinding,
        data: bytes | bytearray | memoryview,
        *,
        media_type: str = DEFAULT_MEDIA_TYPE,
        ttl_seconds: float | None = BLOB_TTL_SECONDS,
    ) -> BlobRef:
        """Keep ``data`` for ``binding``'s view and return the ref that names it.

        The checksum is computed here, over the whole payload, so a client that
        assembles chunks verifies one digest rather than trusting a length. A
        payload above :data:`MAX_BLOB_BYTES` is refused: that is a file, not a
        blob, and a view asks for it through a file ref or a job.
        """
        payload = bytes(data)
        _refuse_oversize(payload)
        self._refuse_full(binding)
        ref = BlobRef(
            id=self.token(),
            size=len(payload),
            media_type=media_type or DEFAULT_MEDIA_TYPE,
            checksum=hashlib.sha256(payload).hexdigest(),
            expires_at=_wire_expiry(ttl_seconds),
        )
        self.table.add(
            ref.id, _grant_for(binding, ref, payload, ttl_seconds, self.clock)
        )
        return ref

    def inline_or_blob(
        self,
        binding: ViewBinding,
        data: bytes | bytearray | memoryview,
        *,
        media_type: str = DEFAULT_MEDIA_TYPE,
        cap: int = 256 * 1024,
    ) -> dict[str, Any]:
        """Return a payload inline when it fits ``cap``, and as a blob when it does not.

        This is the shape decision-59 point 1 asks every large-result operation
        to use: the caller gets either ``{"inline_base64": ..., "size": ...}``
        or ``{"blob": BlobRef, "size": ...}`` and never has to measure the
        message itself. The cap defaults to the protocol's inline ceiling; a
        caller may lower it, never raise it, because the dispatcher refuses a
        reply above the ceiling anyway.
        """
        payload = bytes(data)
        if len(payload) <= min(cap, MAX_BLOB_BYTES):
            return {
                "inline_base64": base64.b64encode(payload).decode("ascii"),
                "size": len(payload),
                "media_type": media_type,
            }
        blob = self.mint(binding, payload, media_type=media_type)
        return {"blob": blob.to_wire(), "size": len(payload), "media_type": media_type}

    def read(
        self,
        binding: ViewBinding,
        raw: Any,
        *,
        offset: int = 0,
        length: int | None = None,
    ) -> bytes:
        """Return ``length`` bytes of ``raw`` from ``offset``, or refuse.

        Only ``raw["id"]`` is read, exactly as with a file ref. The checks run
        in the order that tells a foreign caller the least: shape, ownership,
        generation, expiry, then the bounds - a chunk past the end is a caller
        mistake, not something to clamp silently.
        """
        grant = self._lookup(binding, raw)
        size = len(grant.data)
        if offset < 0 or offset > size:
            raise QgisSdkBridgeError(
                f"offset {offset} is outside a blob of {size} bytes"
            )
        end = size if length is None else min(size, offset + max(0, length))
        return grant.data[offset:end]

    def size(self, binding: ViewBinding, raw: Any) -> int:
        """Return the size of ``raw`` without reading it."""
        return len(self._lookup(binding, raw).data)

    def info(self, binding: ViewBinding, raw: Any) -> BlobRef:
        """Return the stored ref (size, media type, checksum) without the bytes."""
        return self._lookup(binding, raw).ref

    def release_view(self, binding: ViewBinding) -> int:
        """Drop every blob ``binding``'s view holds; the bytes go with them."""
        return self.table.release_view(binding.view_id)

    def prune(self, generation: int) -> int:
        """Drop the blobs of every generation before ``generation``."""
        return self.table.prune(generation)

    def _refuse_full(self, binding: ViewBinding) -> None:
        """Refuse a view past the blob ceiling, after sweeping what has expired."""
        if self.table.count(binding.view_id) < MAX_BLOBS_PER_VIEW:
            return
        self.table.drop_expired()
        if self.table.count(binding.view_id) >= MAX_BLOBS_PER_VIEW:
            raise QgisSdkBridgeError(
                f"view {binding.view_id!r} already holds {MAX_BLOBS_PER_VIEW} "
                "blobs; they are released with the view"
            )

    def _lookup(self, binding: ViewBinding, raw: Any) -> BlobGrant:
        """The blob ``raw`` names for ``binding``, or the refusal it deserves."""
        ref_id = raw.get("id") if isinstance(raw, Mapping) else None
        if not isinstance(raw, Mapping) or raw.get("kind") != BLOB_REF_KIND:
            _refuse_unknown(ref_id)
        if not isinstance(ref_id, str) or not ref_id:
            _refuse_unknown(ref_id)
        grant = self.table.get(ref_id)
        if grant is None or grant.view_id != binding.view_id:
            _refuse_unknown(ref_id)
        if grant.generation != binding.generation:
            raise QgisSdkStaleHandleError(
                f"blob ref {ref_id!r} belongs to a runtime generation that was replaced"
            )
        self._refuse_expired(grant, ref_id)
        return grant

    def _refuse_expired(self, grant: BlobGrant, ref_id: str) -> None:
        """Drop and refuse a blob whose lifetime has run out."""
        if grant.expires_at is not None and self.clock() >= grant.expires_at:
            self.table.drop(ref_id)
            raise QgisSdkStaleHandleError(f"blob ref {ref_id!r} expired")


def _refuse_oversize(payload: bytes) -> None:
    """Refuse a payload that is a file wearing a blob's clothes."""
    if len(payload) > MAX_BLOB_BYTES:
        raise QgisSdkBridgeError(
            f"a blob carries at most {MAX_BLOB_BYTES} bytes; {len(payload)} "
            "is a file, and a view reaches one through a file ref"
        )


def _refuse_unknown(ref_id: Any) -> Never:
    """Refuse an id this view does not hold, said the same way whatever the reason."""
    raise QgisSdkUnknownHandleError(f"blob ref {ref_id!r} is not one this view holds")


def _wire_expiry(ttl_seconds: float | None) -> str | None:
    """The wall-clock moment a client can show, or ``None`` for a blob that does not expire.

    The refusal uses the monotonic clock, which cannot be reordered by a system
    clock change; the wire carries a moment a page can display.
    """
    if ttl_seconds is None:
        return None
    return datetime.fromtimestamp(time.time() + ttl_seconds, tz=UTC).isoformat()


def _grant_for(
    binding: ViewBinding,
    ref: BlobRef,
    payload: bytes,
    ttl_seconds: float | None,
    clock: Callable[[], float],
) -> BlobGrant:
    """The host's side of ``ref``: the bytes, and when they stop being servable."""
    return BlobGrant(
        ref=ref,
        view_id=binding.view_id,
        generation=binding.generation,
        data=payload,
        expires_at=None if ttl_seconds is None else clock() + ttl_seconds,
    )
