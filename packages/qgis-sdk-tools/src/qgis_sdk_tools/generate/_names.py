"""Names: declared identifiers, the reserved set, and the action and stream records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from qgis_sdk.models.errors import QgisSdkBridgeError

from qgis_sdk_tools.generate._contract import (
    _EMITTER_HELPERS,
    _TS_KEYWORDS,
    HOST_SURFACE,
    PLUGIN_SURFACE,
)


def _declared_name(preferred: Any, fallback: str, *, kind: str, action: str) -> str:
    """Use the manifest's name, refusing one the emitter cannot declare.

    A declared name becomes an exported type, so it has to be an identifier this
    module does not already use. Refusing here keeps the promise the rest of the
    emitter makes: what cannot be rendered fails at generation with the manifest
    entry to blame, not later in the consumer's build with a TypeScript error
    pointing at a validator body.
    """
    if preferred is None:
        return fallback
    label = kind if kind == "title" else f"{kind}_name"
    if not isinstance(preferred, str):
        raise QgisSdkBridgeError(
            f"{action}: {label} must be a string, got {preferred!r}"
        )
    if not _is_identifier(preferred):
        raise QgisSdkBridgeError(
            f"{action}: {label} {preferred!r} is not a TypeScript identifier"
        )
    if preferred in _TS_KEYWORDS:
        raise QgisSdkBridgeError(
            f"{action}: {label} {preferred!r} is a TypeScript keyword"
        )
    if preferred in _RESERVED_NAMES:
        raise QgisSdkBridgeError(
            f"{action}: {label} {preferred!r} collides with a name the "
            "generated module already declares"
        )
    return preferred


def _is_identifier(value: str) -> bool:
    """Say whether ``value`` can name a type in the emitted module."""
    if not value or not value[0].isascii():
        return False
    if not (value[0].isalpha() or value[0] in "_$"):
        return False
    return all(char.isascii() and (char.isalnum() or char in "_$") for char in value)


def _reserved_names() -> frozenset[str]:
    """Return every identifier the emitted module declares for itself."""
    names = set(_EMITTER_HELPERS) | _TS_KEYWORDS
    for surface in (PLUGIN_SURFACE, HOST_SURFACE):
        names.update(
            {
                surface.operations_type,
                surface.factory,
                surface.id_const,
                surface.fingerprint_const,
                surface.version_const,
                surface.operations_const,
                surface.operation_id_type,
                surface.options_type,
                surface.client_type,
                surface.error_type,
                surface.error_base,
                surface.stream_handlers_type,
                surface.stream_handle_type,
                surface.stream_terminal_type,
            }
        )
    return frozenset(names)


_RESERVED_NAMES = _reserved_names()


SDK_MEMBERS = frozenset({"client", "host", "schema", "ready", "close"})
"""Names ``QgisSdk`` keeps for itself; an operation id cannot start with one."""


def _check_sdk_tree(ids: Iterable[str]) -> None:
    """Refuse ids ``QgisSdk.fromBridgeSchema`` would refuse, at generation time.

    The SDK nests methods under the segments of their ids (``sites.summary``
    is ``qgis.sites.summary``), so an id may not start with a member of the
    instance, may not have an empty segment, and may not be a prefix of
    another id: ``sites`` cannot be a method and hold ``sites.summary``.
    """
    ordered = sorted(ids)
    for id in ordered:
        segments = id.split(".")
        if segments[0] in SDK_MEMBERS:
            raise QgisSdkBridgeError(
                f"operation id {id!r} shadows a QgisSdk member; "
                f"rename the action (reserved: {', '.join(sorted(SDK_MEMBERS))})"
            )
        if "" in segments:
            raise QgisSdkBridgeError(
                f"operation id {id!r} has an empty segment; QgisSdk nests "
                "methods by the dots in an id"
            )
    for index, id in enumerate(ordered):
        prefix = id + "."
        extended = next(
            (other for other in ordered[index + 1 :] if other.startswith(prefix)), None
        )
        if extended is not None:
            raise QgisSdkBridgeError(
                f"operation id {id!r} is a prefix of {extended!r}; QgisSdk cannot "
                f"make {id!r} both a method and the namespace of the other"
            )


@dataclass(frozen=True, slots=True)
class _Action:
    """One action, with the names its generated pieces are given."""

    id: str
    base: str
    request: Mapping[str, Any]
    result: Mapping[str, Any]
    takes_input: bool
    request_name: str | None = None
    result_name: str | None = None


@dataclass(frozen=True, slots=True)
class _Stream:
    """One declared stream: a request in, one payload schema per event kind out."""

    id: str
    base: str
    request: Mapping[str, Any]
    events: tuple[tuple[str, Mapping[str, Any]], ...]
    request_name: str | None = None

    @property
    def event_type(self) -> str:
        """The name of the discriminated union and of its predicate."""
        return f"{self.base}Event"
