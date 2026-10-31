"""The reference a view holds for a payload too large to travel inline.

decision-59: a payload up to an inline cap crosses the channel as it always did;
above it the host keeps the bytes and hands over a ``BlobRef`` - an opaque id,
the size, the media type, a SHA-256 checksum and an expiry - and the client asks
for bounded chunks through ``qgis.host.blob``.

A ``BlobRef`` is not a ``FileRef`` (decision-20). A file ref names something on
disk that the host was granted: it survives as long as the grant does and the
path is re-checked on every use. A blob is the host's own copy of bytes it
produced for one view, it is never resolved to a path, and it dies with the view
that received it - so a page cannot make the host read a file by inventing a
checksum, and a stale id from a replaced generation is refused like every other
handle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["BLOB_REF", "BLOB_REF_KIND", "BlobRef"]

#: The ``kind`` brand of a blob reference. It is deliberately not ``file`` or
#: ``directory``: the two refs are resolved by different code paths, and a value
#: that can be passed where the other is declared would be a hole.
BLOB_REF_KIND = "blob"

#: The wire shape of a ref. ``title`` names the generated TypeScript type, and
#: ``kind`` is the brand: a bare id cannot be passed where a ``BlobRef`` is
#: declared.
BLOB_REF: dict[str, Any] = {
    "type": "object",
    "title": "BlobRef",
    "properties": {
        "kind": {"enum": [BLOB_REF_KIND]},
        "id": {"type": "string", "pattern": "[a-f0-9]{16,64}"},
        "size": {"type": "integer", "minimum": 0},
        "media_type": {"type": "string"},
        "checksum": {"type": "string", "pattern": "[a-f0-9]{64}"},
        "expires_at": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["kind", "id", "size", "media_type", "checksum"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class BlobRef:
    """What a view holds instead of the bytes: an id and what they are.

    ``checksum`` is the SHA-256 of the whole payload, in lower-case hex, not of
    a chunk: a client verifies once, after it has assembled every chunk, and a
    mismatch is a failed transfer rather than a plausible one. ``expires_at`` is
    the moment the host will refuse the ref, in UTC ISO-8601, and ``None`` when
    it lives only as long as the view does.
    """

    id: str
    size: int
    media_type: str
    checksum: str
    expires_at: str | None = None
    kind: str = BLOB_REF_KIND

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "size": self.size,
            "media_type": self.media_type,
            "checksum": self.checksum,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_wire(cls, value: Any) -> BlobRef:
        """Rebuild a ref from its wire shape; a value already a ref passes."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict) or value.get("kind") != BLOB_REF_KIND:
            raise ValueError(
                "a BlobRef is a {kind, id, size, media_type, checksum} object"
            )
        blob_id = value.get("id")
        if not isinstance(blob_id, str) or not blob_id:
            raise ValueError("a BlobRef carries a non-empty string id")
        size = value.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError("a BlobRef carries a non-negative integer size")
        media_type = value.get("media_type")
        if not isinstance(media_type, str) or not media_type:
            raise ValueError("a BlobRef carries a media type")
        checksum = value.get("checksum")
        if not isinstance(checksum, str) or not checksum:
            raise ValueError("a BlobRef carries a checksum")
        expires_at = value.get("expires_at")
        return cls(
            id=blob_id,
            size=size,
            media_type=media_type,
            checksum=checksum,
            expires_at=None if expires_at is None else str(expires_at),
        )
