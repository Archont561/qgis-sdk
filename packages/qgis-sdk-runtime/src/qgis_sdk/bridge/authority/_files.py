"""File grants: the refs a view was handed, and what each one still allows."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Never

from qgis_sdk.bridge.dispatch import ViewBinding
from qgis_sdk.models import (
    QgisSdkBridgeError,
    QgisSdkGrantRefusedError,
    QgisSdkStaleHandleError,
    QgisSdkUnknownHandleError,
)
from qgis_sdk.models.files import FILE_REF_KINDS, FileRef

from ._grants import FileOperation, _FileGrant, _identity, _Table

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

    def grant(self, binding: ViewBinding, target: _Target) -> _FileGrant:
        """The host's side of ``target``, spelled as this policy declares it."""
        return _FileGrant(
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


@dataclass
class _FileGrants:
    """Mint, resolve and revoke the file refs of every view of one host."""

    clock: Callable[[], float]
    token: Callable[[], str]
    table: _Table = field(init=False)
    revoked: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.table = _Table(self.clock)

    def mint(
        self, binding: ViewBinding, path: str | os.PathLike[str], policy: FilePolicy
    ) -> FileRef:
        """Mint a ref for ``path`` that only ``binding``'s view can use.

        A read grant needs an existing regular file; a write grant needs an
        existing parent directory and, to replace an existing file,
        ``overwrite=True`` - a save dialog that confirmed the overwrite is the
        usual reason to pass it. The path is canonicalised here, once, and the
        ref names that canonical file from now on.
        """
        allowed = policy.allowed()
        _refuse_source(policy.source)
        _refuse_too_many(binding, self.table.count(binding.view_id))
        canonical = _canonical(Path(path).expanduser(), allowed)
        ref = FileRef(
            id=self.token(),
            name=canonical.name,
            operations=tuple(sorted(op.value for op in allowed)),
        )
        identity = _identity(canonical) if FileOperation.READ in allowed else None
        target = _Target(ref, canonical, identity, policy.expiry(self.clock))
        self.table.add(ref.id, policy.grant(binding, target))
        return ref

    def mint_directory(
        self,
        binding: ViewBinding,
        path: str | os.PathLike[str],
        *,
        source: str = "plugin",
        ttl_seconds: float | None = None,
    ) -> FileRef:
        """Mint a read ref for an existing directory that only ``binding`` can use.

        What ``DirectoryInput()`` hands a handler: the directory is resolved
        once, the ref names that canonical directory, and it goes stale when the
        directory is replaced or removed. A directory ref reads; writing into
        one is a separate file grant inside it.
        """
        policy = FilePolicy(source=source, ttl_seconds=ttl_seconds, max_bytes=0)
        _refuse_source(policy.source)
        _refuse_too_many(binding, self.table.count(binding.view_id))
        canonical = _existing_directory(path)
        ref = FileRef(
            id=self.token(),
            name=canonical.name or str(canonical),
            operations=(FileOperation.READ.value,),
            kind="directory",
        )
        target = _Target(
            ref, canonical, _identity(canonical), policy.expiry(self.clock)
        )
        self.table.add(ref.id, policy.grant(binding, target))
        return ref

    def resolve(self, binding: ViewBinding, raw: Any, operation: FileOperation) -> Path:
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
            return _readable(grant)
        return _writable(grant)

    def export(self, binding: ViewBinding, raw: Any, content: str | bytes) -> int:
        """Write ``content`` to the file a write ref names; return the byte count.

        The write is atomic: the bytes go to a temporary file beside the
        destination and replace it in one step, so a failure half-way leaves
        the previous file intact and no partial file behind.
        """
        grant = self._lookup(binding, raw)
        path = self.resolve(binding, raw, FileOperation.WRITE)
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        if len(data) > grant.max_bytes:
            raise QgisSdkGrantRefusedError(
                f"file ref {grant.ref.id!r} allows exports up to {grant.max_bytes} "
                f"bytes; this one is {len(data)}"
            )
        _write_atomically(path, data)
        return len(data)

    def refs(self, binding: ViewBinding) -> tuple[FileRef, ...]:
        """The live refs of ``binding``'s view in its generation, oldest first."""
        now = self.clock()
        return tuple(
            grant.ref
            for _, grant in self.table.held_by(binding.view_id)
            if grant.generation == binding.generation
            and (grant.expires_at is None or now < grant.expires_at)
        )

    def revoke(self, ref_id: str) -> bool:
        """Withdraw one ref; the view is told ``stale_handle`` from now on."""
        grant = self.table.drop(ref_id)
        if grant is None:
            return False
        self.revoked[ref_id] = grant.view_id
        return True

    def release_view(self, binding: ViewBinding) -> int:
        """Forget everything minted for ``binding``'s view; files are untouched.

        Returns how many file refs were dropped. Revocation tombstones go too:
        a view that was released starts over, and its old ids are unknown.
        """
        dropped = self.table.release_view(binding.view_id)
        for ref_id in [k for k, v in self.revoked.items() if v == binding.view_id]:
            del self.revoked[ref_id]
        return dropped

    def prune(self, generation: int) -> int:
        """Drop the refs of every generation before ``generation``."""
        return self.table.prune(generation)

    def _lookup(self, binding: ViewBinding, raw: Any) -> _FileGrant:
        """The grant ``raw`` names for ``binding``, or the refusal it deserves."""
        ref_id = _ref_id(raw)
        grant = self.table.get(ref_id)
        if grant is None:
            _refuse_missing(ref_id, self.revoked, binding)
        _refuse_foreign(grant, binding, raw, ref_id)
        if grant.generation != binding.generation:
            raise QgisSdkStaleHandleError(
                f"file ref {ref_id!r} belongs to a runtime generation that was replaced"
            )
        self._refuse_expired(grant, ref_id)
        return grant

    def _refuse_expired(self, grant: _FileGrant, ref_id: str) -> None:
        """Drop and refuse a grant whose lifetime has run out."""
        if grant.expires_at is not None and self.clock() >= grant.expires_at:
            self.table.drop(ref_id)
            raise QgisSdkStaleHandleError(f"file ref {ref_id!r} expired")


def _refuse_missing(
    ref_id: str, revoked: Mapping[str, str], binding: ViewBinding
) -> Never:
    """Refuse a ref the table no longer holds: revoked for this view, or never held."""
    if revoked.get(ref_id) == binding.view_id:
        raise QgisSdkStaleHandleError(f"file ref {ref_id!r} was revoked")
    raise _refuse_unknown(ref_id)


def _refuse_foreign(
    grant: _FileGrant, binding: ViewBinding, raw: Any, ref_id: str
) -> Never:
    """Refuse a grant that belongs to another view, or names another kind of ref."""
    if grant.view_id != binding.view_id or grant.ref.kind != raw["kind"]:
        raise _refuse_unknown(ref_id)


def _refuse_unknown(ref_id: str) -> QgisSdkUnknownHandleError:
    return QgisSdkUnknownHandleError(f"file ref {ref_id!r} is not one this view holds")


def _ref_id(raw: Any) -> str:
    """The id ``raw`` names, or the refusal for a value that is not shaped like a ref."""
    ref_id = raw.get("id") if isinstance(raw, Mapping) else None
    shaped = isinstance(raw, Mapping) and raw.get("kind") in FILE_REF_KINDS
    if not shaped or not isinstance(ref_id, str) or not ref_id:
        raise _refuse_unknown(str(ref_id))
    return ref_id


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


def _refuse_source(source: str) -> None:
    """Refuse a grant whose origin is neither a picker nor the plugin itself."""
    if source not in FILE_SOURCES:
        raise QgisSdkBridgeError(
            f"{source!r} is not a file grant source; use picker or plugin"
        )


def _refuse_too_many(binding: ViewBinding, held: int) -> None:
    """Refuse the ref past the per-view ceiling."""
    if held >= MAX_FILE_REFS_PER_VIEW:
        raise QgisSdkBridgeError(
            f"view {binding.view_id!r} already holds {MAX_FILE_REFS_PER_VIEW} "
            "file refs; release some before granting more"
        )


def _canonical(path: Path, allowed: frozenset[FileOperation]) -> Path:
    """The canonical file a grant names, or the refusal for a path that is not one."""
    if FileOperation.READ in allowed:
        return _existing_file(path)
    return _writable_target(path)


def _existing_file(path: Path) -> Path:
    """Resolve an existing regular file, or refuse to grant it."""
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        resolved = None
    if resolved is None or not resolved.is_file():
        raise QgisSdkBridgeError(f"{path.name!r} is not a file that exists")
    return resolved


def _writable_target(path: Path) -> Path:
    """The file a write grant names, inside a directory that exists."""
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


def _existing_directory(path: str | os.PathLike[str]) -> Path:
    """Resolve an existing directory, or refuse to grant it."""
    given = Path(path).expanduser()
    try:
        canonical = given.resolve(strict=True)
    except OSError:
        canonical = None
    if canonical is None or not canonical.is_dir():
        raise QgisSdkBridgeError(f"{given.name!r} is not a directory that exists")
    return canonical


def _readable(grant: _FileGrant) -> Path:
    """The path a read grant names, or the refusal when it is no longer that file."""
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


def _writable(grant: _FileGrant) -> Path:
    """The path a write grant names, or the refusal when it may no longer be written."""
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


def _write_atomically(path: Path, data: bytes) -> None:
    """Replace ``path`` with ``data`` in one step, or leave the old file intact."""
    descriptor, name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".part"
    )
    partial = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        partial.replace(path)
    except OSError as error:
        partial.unlink(missing_ok=True)
        reason = getattr(error, "strerror", None) or str(error)
        raise QgisSdkBridgeError(f"export of {path.name!r} failed: {reason}")
