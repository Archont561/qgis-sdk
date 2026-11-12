from __future__ import annotations

import os as _os
import shutil as _shutil
import stat as _stat
import time as _time
import zipfile as _zipfile
from pathlib import Path as _Path

from qgis_sdk_tools.bundle.vendor import (
    RUNTIME_PACKAGE as _RUNTIME_PACKAGE,
)
from qgis_sdk_tools.bundle.vendor import (
    rewrite_imports,
)
from qgis_sdk_tools.bundle.vendor import (
    runtime_files as _runtime_files,
)
from qgis_sdk_tools.bundle.vendor import (
    runtime_source as _runtime_source,
)

from ._errors import ZIP_EPOCH


def stage_runtime(vendor: _Path, *, prefix: str, include_http: bool) -> None:
    """Copy the runtime under ``vendor/qgis_sdk`` with its imports rewritten."""
    vendor.mkdir(parents=True, exist_ok=True)
    (vendor / "__init__.py").write_text(
        '"""Runtime shipped with this plugin by `qgis-sdk build`; see NOTICE."""\n',
        encoding="utf-8",
        newline="\n",
    )
    source_root = _runtime_source()
    for relative in _runtime_files():
        if relative.parts[0] == "http" and not include_http:
            continue
        source = source_root / relative
        target = vendor / _RUNTIME_PACKAGE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".py":
            target.write_text(
                rewrite_imports(source.read_text(encoding="utf-8"), prefix=prefix),
                encoding="utf-8",
                newline="\n",
            )
        else:
            _shutil.copyfile(source, target)


def write_archive(archive: _Path, staging: _Path, plugin: str) -> tuple[str, ...]:
    """A deterministic ZIP: sorted entries, fixed timestamps, normalised modes."""
    date_time = _timestamp()
    # Sorted by the archive name, not the Path: Windows compares paths
    # case-insensitively, and the order must be the same on every platform.
    entries = sorted(
        (path.relative_to(staging).as_posix(), path)
        for path in (staging / plugin).rglob("*")
        if path.is_file()
    )
    names: list[str] = []
    with _zipfile.ZipFile(archive, "w", compression=_zipfile.ZIP_DEFLATED) as zf:
        for name, path in entries:
            info = _zipfile.ZipInfo(name, date_time=date_time)
            info.compress_type = _zipfile.ZIP_DEFLATED
            info.create_system = 3  # unix, so the mode below is honoured
            info.external_attr = (_stat.S_IFREG | 0o644) << 16
            zf.writestr(info, path.read_bytes())
            names.append(name)
    return tuple(names)


def _timestamp() -> tuple[int, int, int, int, int, int]:
    """``SOURCE_DATE_EPOCH`` when set (reproducible-builds convention), else 1980."""
    epoch = _os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch:
        return ZIP_EPOCH
    moment = _time.gmtime(int(epoch))
    return (
        max(moment.tm_year, 1980),
        moment.tm_mon,
        moment.tm_mday,
        moment.tm_hour,
        moment.tm_min,
        moment.tm_sec,
    )
