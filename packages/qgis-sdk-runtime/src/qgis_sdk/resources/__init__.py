"""Reviewed resources shipped inside the package.

A style is requested by its catalog identifier, never by a path the caller
builds: the catalog is what "reviewed" means, and :func:`style_path` resolves the
file from the installed package so a plugin cannot silently load a style from
somewhere else on disk (decision-16).

The styles here are symbology only. They carry no CRS requirement, because every
symbol dimension is expressed in millimetres and no data-defined expression is
used; a style that needed a projected CRS would have to state it on its
``StyleSpec`` before it could be applied safely.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from qgis_sdk.models import (
    QgisSdkPackagedResourceError,
    QgisSdkStyleNotFoundError,
    StyleSpec,
)

STYLE_DIRECTORY = Path(__file__).resolve().parent / "styles"

STYLE_CATALOG: Mapping[str, StyleSpec] = MappingProxyType(
    {
        "reference/point-output": StyleSpec(
            id="reference/point-output",
            resource="reference-point-output.qml",
            geometry_type="point",
            required_fields=("id", "value"),
        ),
        "reference/line-output": StyleSpec(
            id="reference/line-output",
            resource="reference-line-output.qml",
            geometry_type="line",
            required_fields=("id",),
        ),
        # What the reference workflow's buffer step applies to its output: a
        # polygon fill that needs only the identifier the source carried.
        "reference/polygon-output": StyleSpec(
            id="reference/polygon-output",
            resource="reference-polygon-output.qml",
            geometry_type="polygon",
            required_fields=("id",),
        ),
    }
)

#: The directory inside a plugin package where ``@toolbar(icon=...)`` looks.
ICON_DIRECTORY_NAME = "icons"

__all__ = [
    "ICON_DIRECTORY_NAME",
    "STYLE_CATALOG",
    "STYLE_DIRECTORY",
    "icon_path",
    "require_style",
    "style_path",
]


def require_style(style: str) -> StyleSpec:
    """Return the reviewed specification for a style identifier."""
    try:
        return STYLE_CATALOG[style]
    except KeyError:
        raise QgisSdkStyleNotFoundError(style) from None


def style_path(style: str) -> Path:
    """Resolve a reviewed style to the file shipped inside the package."""
    spec = require_style(style)
    path = STYLE_DIRECTORY / spec.resource
    if not path.is_file():
        raise QgisSdkPackagedResourceError(style, f"{spec.resource} is not packaged")
    return path


def icon_path(package_directory: Path, icon: str) -> Path:
    """Resolve ``@toolbar(icon="buffer.svg")`` inside ``<package>/icons/``.

    The name is a file name, not a path: a separator or a parent reference
    is refused, so a binding cannot reach outside the plugin's own package.
    A missing file is the same packaging defect a missing style is - and the
    one ``qgis-sdk check`` reports before the plugin ever loads.
    """
    if not icon or Path(icon).name != icon or icon in (".", ".."):
        raise QgisSdkPackagedResourceError(
            icon, "an icon is a file name under the package's icons/ directory"
        )
    path = package_directory / ICON_DIRECTORY_NAME / icon
    if not path.is_file():
        raise QgisSdkPackagedResourceError(
            icon, f"{ICON_DIRECTORY_NAME}/{icon} is not in {package_directory.name}"
        )
    return path
