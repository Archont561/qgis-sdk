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
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .models import QgisSdkError, QgisSdkExportFailedError, QgisSdkExportRefusedError


class _CcState1:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn1:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_run_export_p1(_s1):
    try:
        _s1.write(_s1.partial)
    except QgisSdkError:
        raise
    except Exception as error:  # noqa: BLE001
        _s1.error = error
        raise QgisSdkExportFailedError(
            str(_s1.destination), str(_s1.error)
        ) from _s1.error
    if not _s1.partial.is_file():
        raise QgisSdkExportFailedError(
            str(_s1.destination), "the writer produced no file"
        )
    if _s1.plan.source is not None:
        refuse_source_destination(_s1.plan.source, _s1.destination)


def _cc_run_export_p2(_s1):
    try:
        if _s1.plan.overwrite:
            _s1.partial.replace(_s1.destination)
        else:
            # The staging file is on the same filesystem. Creating the link
            # atomically refuses even a destination created during writing.
            _s1.destination.hardlink_to(_s1.partial)
    except FileExistsError as error:
        _s1.error = error
        raise QgisSdkExportRefusedError(
            str(_s1.destination),
            ["the destination exists; pass overwrite=True to replace it"],
        ) from _s1.error
    except OSError as error:
        _s1.error = error
        raise QgisSdkExportFailedError(
            str(_s1.destination), str(_s1.error)
        ) from _s1.error


def _cc_run_export_p3(_s1):
    shutil.rmtree(_s1.staging, ignore_errors=True)


def _cc_run_export_p4(_s1):
    _s1.destination = _s1.plan.destination
    _s1.staging = Path(
        tempfile.mkdtemp(prefix=f".{_s1.destination.name}.", dir=_s1.destination.parent)
    )
    _s1.partial = _s1.staging / _s1.destination.name


def _cc_run_export_p5(_s1):
    try:
        for _p1 in (_cc_run_export_p1, _cc_run_export_p2):
            _r1 = _p1(_s1)
            if isinstance(_r1, _CcReturn1):
                return _r1
    finally:
        for _p1 in (_cc_run_export_p3,):
            _p1(_s1)


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_refuse_source_de_p1(_s):
    if _s.source is None:
        raise ValueError(
            "the layer's source dataset cannot be verified; "
            "open a direct local GeoJSON, GeoPackage or ESRI Shapefile instead"
        )
    if _s.source.reference.resolve() != _s.source.path:
        raise ValueError("the layer's source path has changed; reopen the layer")


def _cc_refuse_source_de_p2(_s):
    if _s.source.device is not None:
        _s.info = _s.source.path.stat()
        if (_s.info.st_dev, _s.info.st_ino) != (_s.source.device, _s.source.inode):
            raise ValueError("the layer's source dataset has changed")
    else:
        try:
            _s.source.reference.stat()
        except FileNotFoundError:
            pass
        else:
            raise ValueError(
                "the layer's virtual source has appeared; reopen the layer"
            )


def _cc_refuse_source_de_p3(_s):
    _s.same = _s.source.path == _s.destination.resolve()
    if not _s.same and _s.source.device is not None:
        try:
            _s.info = _s.destination.stat()
        except FileNotFoundError:
            pass
        else:
            _s.same = (_s.info.st_dev, _s.info.st_ino) == (
                _s.source.device,
                _s.source.inode,
            )
    if _s.same:
        raise ValueError("the destination is the layer's source dataset")


def _cc_refuse_source_de_p4(_s):
    raise QgisSdkExportRefusedError(
        str(_s.destination), [f"source safety check failed: {_s.error}"]
    ) from _s.error


def _cc_refuse_source_de_p5(_s):
    _s.destination = Path(_s.destination)
    try:
        for _p in (
            _cc_refuse_source_de_p1,
            _cc_refuse_source_de_p2,
            _cc_refuse_source_de_p3,
        ):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r
    except (OSError, RuntimeError, ValueError) as error:
        _s.error = error
        for _p in (_cc_refuse_source_de_p4,):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r


def _plan_export_facts1(destination, driver, overwrite, reasons):
    if destination.is_dir():
        reasons.append("the destination is a directory")
    elif destination.exists() and not overwrite:
        reasons.append("the destination exists; pass overwrite=True to replace it")
    if not destination.parent.is_dir():
        reasons.append("the destination's directory does not exist")
    if reasons:
        raise QgisSdkExportRefusedError(str(destination), reasons)
    return ExportPlan(destination=destination, driver=driver or "", overwrite=overwrite)


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


def plan_export(
    destination: Path,
    *,
    overwrite: bool,
    drivers: Mapping[str, str] = EXPORT_DRIVERS,
) -> ExportPlan:
    """Validate ``destination`` and return the plan, or refuse with every reason.

    ``drivers`` is the suffix-to-driver table the destination is checked
    against: OGR's for a vector export, GDAL's for a raster one. Everything
    else - existence, the parent directory, ``overwrite``, staging, the
    source-safety recheck - is the same policy for both, which is why the table
    is a parameter rather than a second function.
    """
    destination = Path(destination)
    reasons: list[str] = []
    driver = drivers.get(destination.suffix.lower())
    if driver is None:
        known = ", ".join(sorted(drivers))
        reasons.append(
            f"unsupported format {destination.suffix or '(no suffix)'!r}; "
            f"the destination must end in one of {known}"
        )
    return _plan_export_facts1(destination, driver, overwrite, reasons)


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
    _s = _CcState(source=source, destination=destination)
    for _p in (_cc_refuse_source_de_p5,):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


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
    _s1 = _CcState1(plan=plan, write=write)
    for _p1 in (_cc_run_export_p4, _cc_run_export_p5):
        _r1 = _p1(_s1)
        if isinstance(_r1, _CcReturn1):
            return _r1.value
    return None
