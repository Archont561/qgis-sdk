"""``Layouts`` over PyQGIS: the layout manager and ``QgsLayoutExporter``.

The curated contract is :class:`~qgis_sdk.services.layouts.Layouts`; this module
is the half that has QGIS in it, and four choices are worth stating.

*A layout is found by name in the project's layout manager.* That is where the
print designer puts one and where a template lands, so nothing here keeps a
second registry that could disagree with what the user sees.

*Rendering is a worker's job, and a task in the task manager.* The service
submits a ``@job`` whose body is :meth:`_NativeLayoutsBackend.render`; the
desktop worker backend runs it as one ``QgsTask``, so the export appears in the
QGIS task bar named after the layout, its bar follows ``ctx.progress`` and its
cancel button asks the job to stop (decision-65). The body therefore holds a
name and plain settings, resolves the layout inside the worker and never carries
a live ``QgsLayout`` from the driving thread - the same recipe QGIS Server uses
when it renders a print layout per request.

*The exporter's result enum decides what a caller hears.* ``Success`` returns
the file, ``Canceled`` raises ``QgisSdkJobCancelledError`` so the job settles as
cancelled, and every other code raises ``QgisSdkExportFailedError`` carrying
``errorMessage()``. Nothing is inferred from the absence of an exception, and
the file is written through :mod:`qgis_sdk.exports`, so a failed render leaves
the previous destination untouched.

*An atlas is iterated here, not by the exporter's static overloads.* Those name
the files themselves from the layout's own file-name expression, which would put
a project setting between the caller's pattern and the file on disk. Seeking the
atlas page by page and exporting each one gives the caller's pattern, the page's
own feature id - the one ``prepareForFeature`` put in the layout's report
context - a progress report per page and a cancellation check between them.
"""

from __future__ import annotations

import tempfile as _tempfile
from pathlib import Path as _Path
from typing import Any as _Any

from qgis_sdk.core import ResourceScope as _ResourceScope
from qgis_sdk.layouts import LayoutService as _LayoutService
from qgis_sdk.layouts import LayoutWiring as _LayoutWiring
from qgis_sdk.models import (
    QgisSdkUnsupportedCapabilityError as _QgisSdkUnsupportedCapabilityError,
)

from ._backend import NativeLayoutsBackend as _NativeLayoutsBackend

__all__ = ["NativeLayouts"]


def _core() -> _Any:
    """Import the QGIS core module, or refuse the capability by name."""
    try:
        from qgis import core
    except ImportError as error:  # pragma: no cover - depends on the host build
        raise _QgisSdkUnsupportedCapabilityError(
            "NativeLayouts",
            "print layouts need PyQGIS; this host imported without qgis.core",
        ) from error
    return core


class NativeLayouts(_LayoutService):
    """``Layouts`` over the project's layout manager and QGIS's exporter.

    ``working_directory`` is where an export lands when the caller gave no
    destination; it defaults to a per-session temporary directory, so an export
    a caller never named is still a file the host owns (decision-20).
    """

    def __init__(
        self,
        scope: _ResourceScope,
        *,
        workers: _Any,
        files: _Any = None,
        working_directory: _Path | None = None,
    ) -> None:
        core = _core()
        self._scope = scope
        self._working_directory = _Path(
            working_directory
            if working_directory is not None
            else _tempfile.mkdtemp(prefix="qgis-sdk-layouts-")
        )
        super().__init__(
            _LayoutWiring(
                backend=_NativeLayoutsBackend(core),
                scope=scope,
                working_directory=self._working_directory,
                workers=workers,
                files=files,
            )
        )
        scope.on_close(self._release)

    @property
    def working_directory(self) -> _Path:
        """Where a destination-less export is written."""
        return self._working_directory

    def _release(self) -> None:
        """Nothing to forget: the layouts belong to the project, not to this adapter."""
