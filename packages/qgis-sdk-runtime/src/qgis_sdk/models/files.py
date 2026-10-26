"""The file reference a view, a form or a Processing dialog hands to a handler.

A ``FileRef`` is authority, not a path (decision-20): the host minted it from a
native picker or an explicit plugin grant, canonicalised the path once, and
resolves the id back to that path on each use. Author code receives the ref
and never a string it could have typed itself. ``kind`` says whether the
grant names one file or a directory; only ``id`` carries authority, the rest
is for display.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["FILE_REF", "FILE_REF_KINDS", "FileRef"]

FILE_REF_KINDS = ("file", "directory")

#: The wire shape of a ref. ``title`` names the generated TypeScript type, and
#: ``kind`` is the brand: a layer id or a free string cannot be passed where a
#: FileRef is declared.
FILE_REF: dict[str, Any] = {
    "type": "object",
    "title": "FileRef",
    "properties": {
        "kind": {"enum": list(FILE_REF_KINDS)},
        "id": {"type": "string", "pattern": "[a-f0-9]{16,64}"},
        "name": {"type": "string"},
        "operations": {"type": "array", "items": {"enum": ["read", "write"]}},
    },
    "required": ["kind", "id"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class FileRef:
    """What a view holds: an opaque id and the fields it may show the user."""

    id: str
    name: str
    operations: tuple[str, ...]
    kind: str = "file"

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "operations": list(self.operations),
        }

    @classmethod
    def from_wire(cls, value: Any) -> FileRef:
        """Rebuild a ref from its wire shape; a value already a ref passes."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict) or value.get("kind") not in FILE_REF_KINDS:
            raise ValueError("a FileRef is a {kind, id, name, operations} object")
        if not isinstance(value.get("id"), str) or not value["id"]:
            raise ValueError("a FileRef carries a non-empty string id")
        return cls(
            id=value["id"],
            name=str(value.get("name", "")),
            operations=tuple(value.get("operations", ())),
            kind=value["kind"],
        )
