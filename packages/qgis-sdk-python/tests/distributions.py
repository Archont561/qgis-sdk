"""A real distribution in a temporary site directory, for build tests.

``qgis-sdk build`` reads an installed distribution's metadata - import roots,
compiled files, requirements, licences - so the fixtures tests need are real
``*.dist-info`` trees next to importable packages, not mocks of
``importlib.metadata``.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def install_fixture(
    site: Path,
    name: str,
    *,
    source: str = "",
    requires: tuple[str, ...] = (),
    compiled: bool = False,
) -> Path:
    """Write ``name`` 1.0 into ``site`` and make this interpreter see it."""
    import_name = name.replace("-", "_")
    package = site / import_name
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(source, encoding="utf-8")
    files = [f"{import_name}/__init__.py"]
    if compiled:
        (package / "_native.so").write_bytes(b"\x7fELF")
        files.append(f"{import_name}/_native.so")
    metadata = site / f"{import_name}-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\n"
        f"Name: {name}\n"
        "Version: 1.0\n" + "".join(f"Requires-Dist: {item}\n" for item in requires),
        encoding="utf-8",
    )
    (metadata / "licenses").mkdir()
    (metadata / "licenses" / "LICENSE").write_text("MIT\n", encoding="utf-8")
    record = [
        *files,
        f"{import_name}-1.0.dist-info/METADATA",
        f"{import_name}-1.0.dist-info/RECORD",
        f"{import_name}-1.0.dist-info/licenses/LICENSE",
    ]
    (metadata / "RECORD").write_text(
        "".join(f"{item},,\n" for item in record), encoding="utf-8"
    )
    importlib.invalidate_caches()
    entry = str(site)
    if entry not in sys.path:
        sys.path.insert(0, entry)
    return package
