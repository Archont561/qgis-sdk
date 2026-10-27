"""File and directory inputs holding a FileRef."""

from __future__ import annotations

from collections.abc import Sequence
from os import PathLike
from pathlib import Path
from typing import Any

from qgis_sdk.models import (
    FileRef,
    QgisSdkBridgeRefusalError,
    QgisSdkFormError,
    QgisSdkUiError,
)
from qgis_sdk.ui.components._base import Input

# -- files ----------------------------------------------------------------------------


class _RefInput(Input):
    """A path chosen by the user, held as the ``FileRef`` ``ctx.files`` minted."""

    def set_path(self, path: str | PathLike[str]) -> None:
        """Mint a ref for ``path`` through ``ctx.files`` and make it the value."""
        files = self._require_ctx("files")
        try:
            ref = self._grant(files, Path(path))
        except (QgisSdkBridgeRefusalError, OSError) as error:
            raise QgisSdkFormError(f"{self._describe()}: {error}") from error
        self._commit(ref)

    def path(self, ref: FileRef | None = None) -> Path | None:
        """The path behind ``ref`` (the current value by default), via ``ctx.files``."""
        ref = self._value if ref is None else ref
        if ref is None:
            return None
        return self._require_ctx("files").resolve(ref)

    def _accept(self, value: object) -> object:
        if value is None:
            return None
        files = self._require_ctx("files")
        try:
            files.resolve(value)
        except QgisSdkBridgeRefusalError as error:
            raise QgisSdkFormError(
                f"{self._describe()}: ref {value.id!r} is unknown to ctx.files ({error})"
            ) from error
        return value

    def _grant(self, files: Any, path: Path) -> FileRef:
        raise NotImplementedError

    def _from_widget(self, value: object) -> None:
        """The file widget hands back a path; it becomes a ref or nothing."""
        if self._syncing:
            return
        if value in (None, ""):
            self._store(None)
            return
        try:
            self.set_path(str(value))
        except (QgisSdkFormError, QgisSdkUiError) as error:
            ctx = self._ctx
            if ctx is not None:
                ctx.notifications.warning(f"{self._describe()}: {error}")


class FileInput(_RefInput):
    """One file; the value is a file ``FileRef`` the plugin's ``ctx.files`` resolves.

    ``filters`` are author globs (``("*.csv", "*.gpkg")``) the dialog offers.
    """

    kind = "file"

    def __init__(
        self,
        name: str | None = None,
        *,
        filters: Sequence[str] = (),
        label: str | None = None,
        value: object = None,
        required: bool = False,
    ) -> None:
        self.filters = tuple(filters)
        super().__init__(name, label=label, value=value, required=required)

    def _grant(self, files: Any, path: Path) -> FileRef:
        return files.grant_file(path)

    def _details(self) -> dict[str, Any]:
        return {"filters": list(self.filters)}


class DirectoryInput(_RefInput):
    """One directory; the value is a directory ``FileRef``."""

    kind = "directory"

    def _grant(self, files: Any, path: Path) -> FileRef:
        return files.grant_directory(path)
