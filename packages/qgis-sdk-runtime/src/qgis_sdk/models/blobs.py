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


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_from_wire_p1(_s):
    if isinstance(_s.value, _s.cls):
        return _CcReturn(_s.value)
    if not isinstance(_s.value, dict) or _s.value.get("kind") != BLOB_REF_KIND:
        raise ValueError("a BlobRef is a {kind, id, size, media_type, checksum} object")
    _s.blob_id = _s.value.get("id")
    if not isinstance(_s.blob_id, str) or not _s.blob_id:
        raise ValueError("a BlobRef carries a non-empty string id")
    _s.size = _s.value.get("size")


def _cc_from_wire_p2(_s):
    if not isinstance(_s.size, int) or isinstance(_s.size, bool) or _s.size < 0:
        raise ValueError("a BlobRef carries a non-negative integer size")
    _s.media_type = _s.value.get("media_type")
    if not isinstance(_s.media_type, str) or not _s.media_type:
        raise ValueError("a BlobRef carries a media type")
    _s.checksum = _s.value.get("checksum")


def _cc_from_wire_p3(_s):
    if not isinstance(_s.checksum, str) or not _s.checksum:
        raise ValueError("a BlobRef carries a checksum")
    _s.expires_at = _s.value.get("expires_at")
    return _CcReturn(
        _s.cls(
            id=_s.blob_id,
            size=_s.size,
            media_type=_s.media_type,
            checksum=_s.checksum,
            expires_at=None if _s.expires_at is None else str(_s.expires_at),
        )
    )


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
        _s = _CcState(cls=cls, value=value)
        for _p in (_cc_from_wire_p1, _cc_from_wire_p2, _cc_from_wire_p3):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r.value
        return None
