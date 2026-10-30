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
* :func:`protect_source` refuses an unknown or changed source, or a destination
  that aliases it, before writing and again immediately before the commit.
* :func:`run_export` stages output beside the destination, then replaces it
  when overwrite was allowed or atomically creates a hard link when it was not.
  It removes the staging directory on failure or success. Publishing without
  overwrite requires a filesystem that supports hard links.

Nothing here imports QGIS, so the policy is tested in the pure suite and the
contract suite holds both backends to it.
"""

from __future__ import annotations

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
    source: SourceIdentity | None = None
    overwrite: bool = False


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
    return ExportPlan(destination=destination, driver=driver or "", overwrite=overwrite)


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """Resolved identity and the provider's original path, possibly relative.

    Re-resolving the original reference detects retargeted symlinks and a
    changed working directory, both of which can change what a provider reads.
    """

    path: Path
    device: int | None
    inode: int | None
    reference: Path


def capture_source(
    source: Path, *, allow_virtual: bool = False
) -> SourceIdentity | None:
    """Capture the opened file's identity; an unknown source must fail closed."""
    try:
        path = Path(source).resolve(strict=not allow_virtual)
        try:
            info = path.stat()
        except FileNotFoundError:
            if allow_virtual:
                return SourceIdentity(path, None, None, Path(source))
            return None
        if not path.is_file():
            return None
        return SourceIdentity(path, info.st_dev, info.st_ino, Path(source))
    except (OSError, RuntimeError, ValueError):
        return None


def refuse_source_destination(source: SourceIdentity | None, destination: Path) -> None:
    """Fail closed unless the destination is distinct from the opened file."""
    destination = Path(destination)
    try:
        if source is None:
            raise ValueError(
                "the layer's source dataset cannot be verified; "
                "open a direct local GeoJSON, GeoPackage or ESRI Shapefile instead"
            )
        if source.reference.resolve() != source.path:
            raise ValueError("the layer's source path has changed; reopen the layer")
        if source.device is not None:
            info = source.path.stat()
            if (info.st_dev, info.st_ino) != (source.device, source.inode):
                raise ValueError("the layer's source dataset has changed")
        else:
            try:
                source.reference.stat()
            except FileNotFoundError:
                pass
            else:
                raise ValueError(
                    "the layer's virtual source has appeared; reopen the layer"
                )
        same = source.path == destination.resolve()
        if not same and source.device is not None:
            try:
                info = destination.stat()
            except FileNotFoundError:
                pass
            else:
                same = (info.st_dev, info.st_ino) == (source.device, source.inode)
        if same:
            raise ValueError("the destination is the layer's source dataset")
    except (OSError, RuntimeError, ValueError) as error:
        raise QgisSdkExportRefusedError(
            str(destination), [f"source safety check failed: {error}"]
        ) from error


def protect_source(plan: ExportPlan, source: SourceIdentity | None) -> ExportPlan:
    """Validate the source now and retain it for the pre-commit recheck."""
    refuse_source_destination(source, plan.destination)
    return ExportPlan(plan.destination, plan.driver, source, plan.overwrite)


def run_export(plan: ExportPlan, write: Callable[[Path], None]) -> None:
    """Run ``write`` against a staged path and commit it to the destination.

    ``write`` receives the path it must produce: the destination's own file
    name inside a staging directory next to it, so a writer that creates
    sidecars (a GeoPackage journal, for one) creates them in the staging
    directory too. Overwrite commits with :meth:`pathlib.Path.replace`; without
    overwrite, :meth:`pathlib.Path.hardlink_to` atomically refuses a destination
    created during the write.
    The staging directory is removed on every exit path. A writer raising an SDK
    error passes through; other writer and commit errors become
    :class:`QgisSdkExportFailedError`.
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
        if plan.source is not None:
            refuse_source_destination(plan.source, destination)
        try:
            if plan.overwrite:
                partial.replace(destination)
            else:
                # The staging file is on the same filesystem. Creating the link
                # atomically refuses even a destination created during writing.
                destination.hardlink_to(partial)
        except FileExistsError as error:
            raise QgisSdkExportRefusedError(
                str(destination),
                ["the destination exists; pass overwrite=True to replace it"],
            ) from error
        except OSError as error:
            raise QgisSdkExportFailedError(str(destination), str(error)) from error
    finally:
        shutil.rmtree(staging, ignore_errors=True)
