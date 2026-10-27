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
through it. Nothing here imports Qt.
"""

from __future__ import annotations

import os
import secrets
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from qgis_sdk.bridge.dispatch import ViewBinding
from qgis_sdk.models import (
    QgisSdkBridgeError,
    QgisSdkGrantRefusedError,
    QgisSdkStaleHandleError,
    QgisSdkUnknownHandleError,
)
from qgis_sdk.models.files import FILE_REF, FILE_REF_KINDS, FileRef
from qgis_sdk.network.grants import NetworkGrant

MAX_FILE_REFS_PER_VIEW = 64
"""Refs one view may hold at once; a picker loop cannot grow the table unbounded."""

DEFAULT_EXPORT_BYTES = 4 * 1024 * 1024
"""Default ceiling for one export: the content crosses the channel as a string."""

FILE_SOURCES = frozenset({"picker", "plugin"})


class FileOperation(str, Enum):
    """What a file grant allows; a grant lists one or both."""

    READ = "read"
    WRITE = "write"


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
class _NetworkGrant:
    grant: NetworkGrant
    generation: int


def _refuse_unknown(ref_id: str) -> QgisSdkUnknownHandleError:
    return QgisSdkUnknownHandleError(f"file ref {ref_id!r} is not one this view holds")


def _identity(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino)


@dataclass
class HostAuthority:
    """Mint, resolve and revoke the refs and grants of every view of one host.

    One instance per dispatcher: the generation in a binding is the
    dispatcher's, and a ref minted in a replaced generation is stale even if
    the same view id comes back.
    """

    clock: Callable[[], float] = time.monotonic
    token: Callable[[], str] = field(default=lambda: secrets.token_hex(16))
    _files: dict[str, _FileGrant] = field(default_factory=dict, repr=False)
    _revoked: dict[str, str] = field(default_factory=dict, repr=False)
    _networks: dict[str, _NetworkGrant] = field(default_factory=dict, repr=False)

    # -- files: minting -----------------------------------------------------

    def grant_file(
        self,
        binding: ViewBinding,
        path: str | os.PathLike[str],
        *,
        operations: Iterable[str | FileOperation] = (FileOperation.READ,),
        overwrite: bool = False,
        source: str = "plugin",
        ttl_seconds: float | None = None,
        max_bytes: int = DEFAULT_EXPORT_BYTES,
    ) -> FileRef:
        """Mint a ref for ``path`` that only ``binding``'s view can use.

        ``source`` records where the authority came from (``picker`` or
        ``plugin``). A read grant needs an existing regular file; a write grant
        needs an existing parent directory and, to replace an existing file,
        ``overwrite=True`` - a save dialog that confirmed the overwrite is the
        usual reason to pass it. The path is canonicalised here, once, and the
        ref names that canonical file from now on.
        """
        try:
            allowed = frozenset(FileOperation(op) for op in operations)
        except ValueError as error:
            raise QgisSdkBridgeError(
                f"a file grant allows read and/or write, not {error}"
            ) from None
        if not allowed:
            raise QgisSdkBridgeError("a file grant allows at least one operation")
        if source not in FILE_SOURCES:
            raise QgisSdkBridgeError(
                f"{source!r} is not a file grant source; use picker or plugin"
            )
        if self._count(binding.view_id) >= MAX_FILE_REFS_PER_VIEW:
            raise QgisSdkBridgeError(
                f"view {binding.view_id!r} already holds {MAX_FILE_REFS_PER_VIEW} "
                "file refs; release some before granting more"
            )
        canonical = self._canonical(Path(path).expanduser(), allowed)
        ref = FileRef(
            id=self.token(),
            name=canonical.name,
            operations=tuple(sorted(op.value for op in allowed)),
        )
        self._files[ref.id] = _FileGrant(
            ref=ref,
            view_id=binding.view_id,
            generation=binding.generation,
            path=canonical,
            operations=allowed,
            overwrite=bool(overwrite),
            source=source,
            max_bytes=int(max_bytes),
            identity=_identity(canonical) if FileOperation.READ in allowed else None,
            expires_at=None if ttl_seconds is None else self.clock() + ttl_seconds,
        )
        return ref

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
        once, the ref names that canonical directory, and it goes stale when
        the directory is replaced or removed. A directory ref reads; writing
        into one is a separate file grant inside it.
        """
        if source not in FILE_SOURCES:
            raise QgisSdkBridgeError(
                f"{source!r} is not a file grant source; use picker or plugin"
            )
        if self._count(binding.view_id) >= MAX_FILE_REFS_PER_VIEW:
            raise QgisSdkBridgeError(
                f"view {binding.view_id!r} already holds {MAX_FILE_REFS_PER_VIEW} "
                "file refs; release some before granting more"
            )
        given = Path(path).expanduser()
        try:
            canonical = given.resolve(strict=True)
        except OSError:
            canonical = None
        if canonical is None or not canonical.is_dir():
            raise QgisSdkBridgeError(f"{given.name!r} is not a directory that exists")
        ref = FileRef(
            id=self.token(),
            name=canonical.name or str(canonical),
            operations=(FileOperation.READ.value,),
            kind="directory",
        )
        self._files[ref.id] = _FileGrant(
            ref=ref,
            view_id=binding.view_id,
            generation=binding.generation,
            path=canonical,
            operations=frozenset({FileOperation.READ}),
            overwrite=False,
            source=source,
            max_bytes=0,
            identity=_identity(canonical),
            expires_at=None if ttl_seconds is None else self.clock() + ttl_seconds,
        )
        return ref

    @staticmethod
    def _canonical(path: Path, allowed: frozenset[FileOperation]) -> Path:
        if FileOperation.READ in allowed:
            try:
                resolved = path.resolve(strict=True)
            except OSError:
                resolved = None
            if resolved is None or not resolved.is_file():
                raise QgisSdkBridgeError(f"{path.name!r} is not a file that exists")
            return resolved
        try:
            parent = path.parent.resolve(strict=True)
        except OSError:
            parent = None
        if parent is None or not parent.is_dir():
            raise QgisSdkBridgeError(
                f"the directory for {path.name!r} does not exist; a write grant "
                "names a file inside an existing directory"
            )
        if not path.name or (path.exists() and not path.is_file()):
            raise QgisSdkBridgeError(f"{path.name!r} is not a file")
        return parent / path.name

    def _count(self, view_id: str) -> int:
        return sum(1 for grant in self._files.values() if grant.view_id == view_id)

    # -- files: resolving ---------------------------------------------------

    def resolve_file(
        self, binding: ViewBinding, raw: Any, operation: FileOperation
    ) -> Path:
        """Return the canonical path behind ``raw`` for ``operation``, or refuse.

        Only ``raw["id"]`` is read; the display fields a page may have edited
        are ignored. The checks run in the order that gives a foreign caller
        the least: shape, ownership, generation, expiry, operation, then the
        file itself.
        """
        grant = self._lookup(binding, raw)
        if operation not in grant.operations:
            raise QgisSdkGrantRefusedError(
                f"file ref {grant.ref.id!r} does not allow {operation.value}"
            )
        if operation is FileOperation.READ:
            return self._readable(grant)
        return self._writable(grant)

    def _lookup(self, binding: ViewBinding, raw: Any) -> _FileGrant:
        ref_id = raw.get("id") if isinstance(raw, Mapping) else None
        if not isinstance(raw, Mapping) or raw.get("kind") not in FILE_REF_KINDS:
            raise _refuse_unknown(str(ref_id))
        if not isinstance(ref_id, str) or not ref_id:
            raise _refuse_unknown(str(ref_id))
        grant = self._files.get(ref_id)
        if grant is None:
            if self._revoked.get(ref_id) == binding.view_id:
                raise QgisSdkStaleHandleError(f"file ref {ref_id!r} was revoked")
            raise _refuse_unknown(ref_id)
        if grant.view_id != binding.view_id or grant.ref.kind != raw["kind"]:
            raise _refuse_unknown(ref_id)
        if grant.generation != binding.generation:
            raise QgisSdkStaleHandleError(
                f"file ref {ref_id!r} belongs to a runtime generation that was replaced"
            )
        if grant.expires_at is not None and self.clock() >= grant.expires_at:
            del self._files[ref_id]
            raise QgisSdkStaleHandleError(f"file ref {ref_id!r} expired")
        return grant

    @staticmethod
    def _readable(grant: _FileGrant) -> Path:
        try:
            current = grant.path.resolve(strict=True)
        except OSError:
            current = None
        directory = grant.ref.kind == "directory"
        still_there = grant.path.is_dir() if directory else grant.path.is_file()
        if (
            current != grant.path
            or not still_there
            or _identity(grant.path) != grant.identity
        ):
            what = "directory" if directory else "file"
            raise QgisSdkStaleHandleError(
                f"file ref {grant.ref.id!r} no longer names the {what} that was granted"
            )
        return grant.path

    @staticmethod
    def _writable(grant: _FileGrant) -> Path:
        path = grant.path
        try:
            parent = path.parent.resolve(strict=True)
        except OSError:
            parent = None
        if parent != path.parent or path.is_symlink():
            raise QgisSdkStaleHandleError(
                f"file ref {grant.ref.id!r} no longer names the destination that "
                "was granted"
            )
        if path.exists():
            if not path.is_file():
                raise QgisSdkStaleHandleError(
                    f"file ref {grant.ref.id!r} no longer names a file"
                )
            if not grant.overwrite:
                raise QgisSdkGrantRefusedError(
                    f"file ref {grant.ref.id!r} does not allow overwriting the "
                    "existing file"
                )
        return path

    def export_file(self, binding: ViewBinding, raw: Any, content: str | bytes) -> int:
        """Write ``content`` to the file a write ref names; return the byte count.

        The write is atomic: the bytes go to a temporary file beside the
        destination and replace it in one step, so a failure half-way leaves
        the previous file intact and no partial file behind.
        """
        grant = self._lookup(binding, raw)
        path = self.resolve_file(binding, raw, FileOperation.WRITE)
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        if len(data) > grant.max_bytes:
            raise QgisSdkGrantRefusedError(
                f"file ref {grant.ref.id!r} allows exports up to {grant.max_bytes} "
                f"bytes; this one is {len(data)}"
            )
        descriptor, name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".part"
        )
        partial = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(partial, path)
        except OSError as error:
            partial.unlink(missing_ok=True)
            reason = getattr(error, "strerror", None) or str(error)
            raise QgisSdkBridgeError(f"export of {path.name!r} failed: {reason}")
        return len(data)

    # -- files: revocation and release -------------------------------------

    def refs(self, binding: ViewBinding) -> tuple[FileRef, ...]:
        """The live refs of ``binding``'s view in its generation, oldest first."""
        return tuple(
            grant.ref
            for grant in self._files.values()
            if grant.view_id == binding.view_id
            and grant.generation == binding.generation
            and (grant.expires_at is None or self.clock() < grant.expires_at)
        )

    def revoke(self, ref_id: str) -> bool:
        """Withdraw one ref; the view is told ``stale_handle`` from now on."""
        grant = self._files.pop(ref_id, None)
        if grant is None:
            return False
        self._revoked[ref_id] = grant.view_id
        return True

    def release_view(self, binding: ViewBinding) -> int:
        """Forget everything minted for ``binding``'s view; files are untouched.

        Returns how many file refs were dropped. Revocation tombstones go too:
        a view that was released starts over, and its old ids are unknown.
        """
        dropped = [
            ref_id
            for ref_id, grant in self._files.items()
            if grant.view_id == binding.view_id
        ]
        for ref_id in dropped:
            del self._files[ref_id]
        for ref_id in [k for k, v in self._revoked.items() if v == binding.view_id]:
            del self._revoked[ref_id]
        self._networks.pop(binding.view_id, None)
        return len(dropped)

    def prune(self, generation: int) -> int:
        """Drop refs and grants from generations before ``generation``."""
        stale = [
            ref_id
            for ref_id, grant in self._files.items()
            if grant.generation < generation
        ]
        for ref_id in stale:
            del self._files[ref_id]
        for view_id in [
            view_id
            for view_id, granted in self._networks.items()
            if granted.generation < generation
        ]:
            del self._networks[view_id]
        return len(stale)

    # -- network ------------------------------------------------------------

    def grant_network(self, binding: ViewBinding, grant: NetworkGrant) -> None:
        """Give ``binding``'s view ``grant``, replacing any earlier one."""
        self._networks[binding.view_id] = _NetworkGrant(grant, binding.generation)

    def network_grant(self, binding: ViewBinding) -> NetworkGrant | None:
        """The view's grant in this generation, or ``None``."""
        granted = self._networks.get(binding.view_id)
        if granted is None or granted.generation != binding.generation:
            return None
        return granted.grant

    def require_network(self, binding: ViewBinding) -> NetworkGrant:
        """The view's grant, or the refusal a network operation reports."""
        grant = self.network_grant(binding)
        if grant is None:
            raise QgisSdkGrantRefusedError("this view holds no network grant")
        return grant

    def revoke_network(self, binding: ViewBinding) -> bool:
        return self._networks.pop(binding.view_id, None) is not None


__all__ = [
    "DEFAULT_EXPORT_BYTES",
    "FILE_REF",
    "FILE_SOURCES",
    "MAX_FILE_REFS_PER_VIEW",
    "FileOperation",
    "FileRef",
    "HostAuthority",
]
