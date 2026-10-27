"""Load a generated catalogue, and the one the runtime ships.

The shipped snapshot (``catalogue.json`` and the provider modules next to
this file) is generated from the pinned QGIS 4 by
``scripts/generate_processing_snapshot.py`` and drift-checked in CI; it is
never edited by hand (decision-64).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from qgis_sdk.models import Catalogue

__all__ = ["CORE_PROVIDERS", "core_catalogue", "load_catalogue"]

#: The providers the runtime's snapshot covers: what every QGIS 4 ships.
CORE_PROVIDERS: tuple[str, ...] = ("native", "qgis", "gdal", "3d", "pdal")
_SNAPSHOT = Path(__file__).with_name("catalogue.json")


@cache
def load_catalogue(path: Path) -> Catalogue:
    """Parse one ``catalogue.json`` once per path."""
    return Catalogue.from_json(Path(path).read_text(encoding="utf-8"))


def core_catalogue() -> Catalogue:
    """The catalogue of the core providers shipped with this runtime."""
    return load_catalogue(_SNAPSHOT)
