"""The export policy every ``Layers`` backend shares (decision-19).

Exporting a permanent result is an explicit act: the caller names the
destination, says whether an existing file may be replaced, and gets either the
file or a refusal that names every problem at once. What the backends differ in
is only *how bytes are produced* - OGR for the native adapter, a copy for the
fake - so that part is injected as a ``write`` callable and everything around it
lives here, once:

* :func:`plan_export` checks the destination before anything is written: a
  known suffix, an existing parent directory, not a directory itself, and
  ``overwrite`` for a file that is already there.
* :func:`run_export` stages the writer's output in a fresh directory **beside**
  the destination, commits it with one ``os.replace`` when the writer returned,
  and removes the staging directory whatever happened. A failure therefore
  leaves the destination exactly as it was - absent, or still the old file when
  ``overwrite`` was requested - and no partial file, journal or sidecar behind.

Nothing here imports QGIS, so the policy is tested in the pure suite and the
contract suite holds both backends to it.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .models import QgisSdkError, QgisSdkExportFailedError, QgisSdkExportRefusedError

__all__ = ["EXPORT_DRIVERS", "ExportPlan", "plan_export", "run_export"]

#: Destination suffix (lower-case) -> OGR driver name. Two formats on purpose:
#: the reference workflow needs one text and one container format, and every
#: addition is a packaging and qualification decision, not a convenience.
EXPORT_DRIVERS = MappingProxyType({".geojson": "GeoJSON", ".gpkg": "GPKG"})


@dataclass(frozen=True, slots=True)
class ExportPlan:
    """A destination that passed every precondition, and the driver for it."""

    destination: Path
    driver: str


def plan_export(destination: Path, *, overwrite: bool) -> ExportPlan:
    """Validate ``destination`` and return the plan, or refuse with every reason."""
    destination = Path(destination)
    reasons: list[str] = []
    driver = EXPORT_DRIVERS.get(destination.suffix.lower())
    if driver is None:
        known = ", ".join(sorted(EXPORT_DRIVERS))
        reasons.append(
            f"unsupported format {destination.suffix or '(no suffix)'!r}; "
            f"the destination must end in one of {known}"
        )
    if destination.is_dir():
        reasons.append("the destination is a directory")
    elif destination.exists() and not overwrite:
        reasons.append("the destination exists; pass overwrite=True to replace it")
    if not destination.parent.is_dir():
        reasons.append("the destination's directory does not exist")
    if reasons:
        raise QgisSdkExportRefusedError(str(destination), reasons)
    return ExportPlan(destination=destination, driver=driver or "")


def run_export(plan: ExportPlan, write: Callable[[Path], None]) -> None:
    """Run ``write`` against a staged path and commit it to the destination.

    ``write`` receives the path it must produce: the destination's own file
    name inside a staging directory next to it, so a writer that creates
    sidecars (a GeoPackage journal, for one) creates them in the staging
    directory too. The commit is a single ``os.replace``; the staging directory
    is removed on every exit path. A writer raising an SDK error passes
    through; any other exception becomes :class:`QgisSdkExportFailedError`.
    """
    destination = plan.destination
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    partial = staging / destination.name
    try:
        try:
            write(partial)
        except QgisSdkError:
            raise
        except Exception as error:
            raise QgisSdkExportFailedError(str(destination), str(error)) from error
        if not partial.is_file():
            raise QgisSdkExportFailedError(
                str(destination), "the writer produced no file"
            )
        os.replace(partial, destination)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
