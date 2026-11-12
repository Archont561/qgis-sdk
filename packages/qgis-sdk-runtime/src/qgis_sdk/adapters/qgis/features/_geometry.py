"""Geometry encoding and decoding between QGIS and the wire."""

from __future__ import annotations

import base64

from qgis.core import QgsGeometry

from qgis_sdk.models import Geometry, QgisSdkUnsupportedCapabilityError

__all__ = ["decode", "encode"]

#: Flat WKB type code to the SDK's vocabulary. The single-part and multi-part
#: cases stay apart on the wire: a page that draws a multipoint wants to know.
#: Z and M variants are reported as their flat type, which is what a page
#: reasons about.
#: The legacy "25D" bit some providers still set on ``wkbType()``.
_WKB_25D = 0x80000000

_GEOMETRY_NAMES = {
    1: "point",
    2: "line",
    3: "polygon",
    4: "multipoint",
    5: "multiline",
    6: "multipolygon",
    7: "geometrycollection",
}


def geometry_type_code(geometry: QgsGeometry) -> int:
    """The flat WKB type code of a geometry, without Z/M/25D decorations.

    ``WkbType`` is a single enum whose Z, M and ZM variants are the flat code with
    a thousands digit, and whose legacy 25D variants set the high bit; a page
    reasons about "point" and "multipoint", so both decorations are dropped here.
    """
    return (int(geometry.wkbType()) & ~_WKB_25D) % 1000


def vertex_count(geometry: QgsGeometry) -> int:
    """Every vertex of the geometry, parts included."""
    abstract = geometry.constGet()
    return 0 if abstract is None else int(abstract.vertexCount())


def part_count(geometry: QgsGeometry) -> int:
    """Parts of the geometry: one for a single part, N for a collection."""
    abstract = geometry.constGet()
    return 0 if abstract is None else int(abstract.partCount())


def encode(geometry: QgsGeometry, encoding: str, crs: str | None) -> Geometry:
    """Encode one QGIS geometry in the encoding the caller asked for.

    A feature with no geometry is a fact about a row, not an error: a row added
    from the console, or one a provider stores with no shape, still has
    attributes worth a page. ``QgsGeometry`` spells that case ``constGet()``
    returning None, and neither ``isNull()`` nor ``isEmpty()`` says it - a
    default-constructed ``QgsGeometry`` is neither null nor empty by those two
    predicates and still holds no abstract geometry at all.
    """
    abstract = geometry.constGet()
    if abstract is None or geometry.isNull() or geometry.isEmpty():
        value = ""
        if encoding == "wkb" and abstract is not None:
            value = base64.b64encode(bytes(geometry.asWkb())).decode("ascii")
        return Geometry(
            encoding=encoding,
            value=value,
            geometry_type="none" if abstract is None else name(geometry),
            crs=crs,
            part_count=part_count(geometry),
            is_empty=abstract is not None,
        )
    return _encode_phase1(crs, encoding, geometry)


def _encode_phase1(crs, encoding, geometry):
    if encoding == "wkb":
        value = base64.b64encode(bytes(geometry.asWkb())).decode("ascii")
    elif encoding == "wkt":
        value = geometry.asWkt()
    elif encoding == "geojson":
        value = geometry.asJson()
    else:  # pragma: no cover - FeatureQuery refuses it first
        raise QgisSdkUnsupportedCapabilityError(
            f"unknown geometry encoding {encoding!r}"
        )
    return Geometry(
        encoding=encoding,
        value=value,
        geometry_type=name(geometry),
        crs=crs,
        part_count=part_count(geometry),
        vertex_count=vertex_count(geometry),
    )


def name(geometry: QgsGeometry) -> str:
    return _GEOMETRY_NAMES.get(geometry_type_code(geometry), "geometrycollection")


def decode(geometry: Geometry) -> QgsGeometry:
    """Rebuild a QGIS geometry from the wire value a caller sent.

    All three encodings are accepted, because a page that read a WKB geometry may
    well hand a modified copy back; an encoding QGIS cannot parse is refused by
    name rather than becoming a null geometry the caller would never see.
    """
    if geometry.encoding == "wkt":
        decoded = QgsGeometry.fromWkt(geometry.value)
    elif geometry.encoding == "geojson":
        decoded = QgsGeometry.fromJson(geometry.value)
    else:
        decoded = QgsGeometry.fromWkb(base64.b64decode(geometry.value))
    if decoded.isNull():
        raise QgisSdkUnsupportedCapabilityError(
            f"the {geometry.encoding} geometry could not be parsed"
        )
    return decoded
