"""The ``Files`` service over the host authority (decision-20, TASK-68).

One :class:`~qgis_sdk.bridge.authority.HostAuthority` per runtime mints every
ref a plugin ever sees: the page host's, the Processing toolbox's and the
form components' (``FileInput``/``DirectoryInput``). :class:`FilesService`
is that authority seen from one owner - the plugin itself, or one view -
through a binding only the host knows. A ref minted for a page is unknown
to the plugin's service and the other way round, exactly as two views never
see each other's refs; a handler reads only what was granted to it.

Nothing here imports Qt; the fake in :mod:`qgis_sdk.testing` is this very
class over a private authority, so a pure test refuses what a host refuses.
"""

from __future__ import annotations

from collections.abc import Iterable
from os import PathLike
from pathlib import Path
from typing import Any

from qgis_sdk.bridge.authority import FileOperation, HostAuthority
from qgis_sdk.bridge.dispatch import ViewBinding
from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.models.files import FileRef

__all__ = ["FilesService"]


class FilesService:
    """``ctx.files``: mint refs for this owner and resolve the ones it holds.

    ``owner`` names who the refs belong to (``plugin:<id>`` for the plugin's
    own context, a view id for a surface); closing ``scope`` revokes every ref
    the service minted, the way a view's refs go with the view.
    """

    def __init__(
        self,
        authority: HostAuthority,
        scope: ResourceScope,
        *,
        owner: str,
        generation: int = 0,
    ) -> None:
        self._authority = authority
        self._scope = scope
        self.binding = ViewBinding(
            view_id=owner, origin="qgis://plugin", generation=generation
        )
        scope.on_close(self._release)

    @property
    def authority(self) -> HostAuthority:
        """The authority behind this service, for a host that shares one."""
        return self._authority

    def grant_file(
        self,
        path: str | PathLike[str],
        *,
        operations: Iterable[str] = ("read",),
        overwrite: bool = False,
    ) -> FileRef:
        self._scope.ensure_open()
        return self._authority.grant_file(
            self.binding,
            path,
            operations=operations,
            overwrite=overwrite,
            source="plugin",
        )

    def grant_directory(self, path: str | PathLike[str]) -> FileRef:
        self._scope.ensure_open()
        return self._authority.grant_directory(self.binding, path, source="plugin")

    def resolve(self, ref: FileRef | Any, *, operation: str = "read") -> Path:
        self._scope.ensure_open()
        raw = ref.to_wire() if isinstance(ref, FileRef) else ref
        return self._authority.resolve_file(self.binding, raw, FileOperation(operation))

    def _release(self) -> None:
        self._authority.release_view(self.binding)
