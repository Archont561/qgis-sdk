"""The connections TASK-92's contract opens: built, not committed.

A GeoPackage is SQLite with a geometry dialect, so the fixture file is written
here the way ``layer_kind_fixtures`` writes its MBTiles and LAS: ``sqlite3`` is
standard library, the file is deterministic, and a reviewer can read every byte
in this diff instead of guessing at a blob. The three tables are the smallest
set that proves the surface - a line table, a point table and an aspatial one -
and their names, fields and geometries are the *vocabulary*: the fake declares
exactly these and the contract asserts both backends answer alike.

The PostGIS fixture is a connection, not a file: it needs a server. The fake
declares it always; the native backend registers it from
``QGIS_SDK_TEST_POSTGIS`` (a libpq ``key=value`` string naming a test database
that holds ``public.points``) and otherwise the row is recorded as **blocked by
environment** - which is what TASK-92's acceptance criterion allows.

``warehouse`` is the one connection nothing serves: the fake declares it
invalid, and the native side registers it pointing at a dead port with a
password in its settings. One fixture proves three claims - ``test`` answers a
verdict rather than raising, a description carries no secret, and attaching an
authentication configuration replaces the stored password - without a server.
"""

from __future__ import annotations

import sqlite3
import struct
from pathlib import Path


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_write_geopackage_p1(_s):
    _s.database.execute(f"PRAGMA application_id = {GPKG_APPLICATION_ID}")
    _s.database.execute(f"PRAGMA user_version = {GPKG_USER_VERSION}")
    _s.database.execute(
        "CREATE TABLE gpkg_spatial_ref_sys ("
        "srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY, "
        "organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL, "
        "definition TEXT NOT NULL, description TEXT)"
    )


def _cc_write_geopackage_p2(_s):
    _s.database.executemany(
        "INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)",
        (
            ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
            ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
            ("WGS 84 geodetic", 4326, "EPSG", 4326, WGS84_WKT, None),
        ),
    )


def _cc_write_geopackage_p3(_s):
    _s.database.execute(
        "CREATE TABLE gpkg_contents ("
        "table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL, "
        "identifier TEXT UNIQUE, description TEXT DEFAULT '', "
        "last_change DATETIME NOT NULL DEFAULT (datetime('now')), "
        "min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, "
        "srs_id INTEGER, "
        "CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) "
        "REFERENCES gpkg_spatial_ref_sys(srs_id))"
    )


def _cc_write_geopackage_p4(_s):
    _s.database.execute(
        "CREATE TABLE gpkg_geometry_columns ("
        "table_name TEXT NOT NULL, column_name TEXT NOT NULL, "
        "geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL, "
        "z TINYINT NOT NULL, m TINYINT NOT NULL, "
        "PRIMARY KEY (table_name, column_name), "
        "CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) "
        "REFERENCES gpkg_contents(table_name), "
        "CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) "
        "REFERENCES gpkg_spatial_ref_sys(srs_id))"
    )


def _cc_write_geopackage_p5(_s):
    _s.database.execute(
        "CREATE TABLE roads ("
        "fid INTEGER PRIMARY KEY AUTOINCREMENT, geom LINESTRING, name TEXT)"
    )
    _s.database.execute(
        "CREATE TABLE places ("
        "fid INTEGER PRIMARY KEY AUTOINCREMENT, geom POINT, "
        "kind TEXT, name TEXT)"
    )
    _s.database.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, text TEXT)")


def _cc_write_geopackage_p6(_s):
    _s.database.executemany(
        "INSERT INTO gpkg_contents "
        "(table_name, data_type, identifier, min_x, min_y, max_x, max_y, srs_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            (
                GPKG_ROADS,
                "features",
                GPKG_ROADS,
                21.0,
                52.0,
                21.3,
                52.3,
                4326,
            ),
            (
                GPKG_PLACES,
                "features",
                GPKG_PLACES,
                21.0,
                52.0,
                21.1,
                52.1,
                4326,
            ),
            (GPKG_NOTES, "attributes", GPKG_NOTES, None, None, None, None, None),
        ),
    )


def _cc_write_geopackage_p7(_s):
    _s.database.executemany(
        "INSERT INTO gpkg_geometry_columns VALUES (?, ?, ?, ?, 0, 0)",
        (
            (GPKG_ROADS, "geom", "LINESTRING", 4326),
            (GPKG_PLACES, "geom", "POINT", 4326),
        ),
    )


def _cc_write_geopackage_p8(_s):
    _s.database.executemany(
        "INSERT INTO roads (geom, name) VALUES (?, ?)",
        (
            (
                _geometry_blob(2, [x for point in line for x in point]),
                f"road {index}",
            )
            for index, line in enumerate(ROADS, start=1)
        ),
    )


def _cc_write_geopackage_p9(_s):
    _s.database.executemany(
        "INSERT INTO places (geom, kind, name) VALUES (?, ?, ?)",
        ((_geometry_blob(1, [x, y]), kind, name) for x, y, kind, name in PLACES),
    )
    _s.database.executemany(
        "INSERT INTO notes (id, text) VALUES (?, ?)",
        ((index, text) for index, text in enumerate(NOTES, start=1)),
    )


def _cc_write_geopackage_p10(_s):
    _s.path = Path(_s.path)
    _s.path.parent.mkdir(parents=True, exist_ok=True)
    if _s.path.exists():
        _s.path.unlink()
    with sqlite3.connect(_s.path) as _s.database:
        for _p in (
            _cc_write_geopackage_p1,
            _cc_write_geopackage_p2,
            _cc_write_geopackage_p3,
            _cc_write_geopackage_p4,
            _cc_write_geopackage_p5,
            _cc_write_geopackage_p6,
            _cc_write_geopackage_p7,
            _cc_write_geopackage_p8,
            _cc_write_geopackage_p9,
        ):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r
    return _CcReturn(_s.path)


# -- the shared vocabulary ----------------------------------------------------

#: The GeoPackage connection every backend declares, and its file.
GPKG_CONNECTION = "survey"
GPKG_FILE = "survey.gpkg"

#: The GeoPackage's three tables: ``(name, kind, geometries, fields, crs)``.
GPKG_ROADS = "roads"
GPKG_ROADS_KIND = "vector"
GPKG_ROADS_GEOMETRIES = ("line",)
GPKG_ROADS_FIELDS = ("name",)
GPKG_PLACES = "places"
GPKG_PLACES_KIND = "vector"
GPKG_PLACES_GEOMETRIES = ("point",)
GPKG_PLACES_FIELDS = ("kind", "name")
GPKG_NOTES = "notes"
GPKG_NOTES_KIND = "aspatial"
GPKG_NOTES_GEOMETRIES: tuple[str, ...] = ()
GPKG_NOTES_FIELDS = ("text",)
FIXTURE_CRS = "EPSG:4326"

#: The PostGIS connection: declared by the fake always, registered natively only
#: when ``QGIS_SDK_TEST_POSTGIS`` names a server holding ``public.points``.
POSTGIS_CONNECTION = "lagoon"
POSTGIS_SCHEMA = "public"
POSTGIS_POINTS = "points"
POSTGIS_POINTS_KIND = "vector"
POSTGIS_POINTS_GEOMETRIES = ("point",)
POSTGIS_POINTS_FIELDS = ("kind",)

#: The connection nothing serves. Its registered settings carry a password on
#: purpose: the no-secret claim is proven against a secret that exists.
BROKEN_CONNECTION = "warehouse"
BROKEN_PASSWORD = "hunter2-s3cret"
BROKEN_URI = (
    f"dbname='none' host=127.0.0.1 port=1 user='gis' password='{BROKEN_PASSWORD}'"
)

#: The authentication configuration the tests put in the registry. The id is
#: the registry's to choose; the tests keep the one it answers.
AUTH_CONFIG_NAME = "field crew"

# -- GeoPackage writing -------------------------------------------------------

#: The GeoPackage application id: ``GPKG`` as a big-endian fourcc. GDAL refuses
#: a ``.gpkg`` whose pragma does not carry it.
GPKG_APPLICATION_ID = 0x47504B47
#: GeoPackage 1.2, which is what the fixture's tables use.
GPKG_USER_VERSION = 10200

#: EPSG:4326's WKT, the one row ``gpkg_contents`` points at.
WGS84_WKT = (
    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'
)

#: The reference points the rest of the fixtures use, one per table.
ROADS = (((21.0, 52.0), (21.1, 52.1)), ((21.2, 52.2), (21.3, 52.3)))
PLACES = ((21.0, 52.0, "park", "Saxon"), (21.1, 52.1, "school", "Primary"))
NOTES = ("a boundary stone, recut 1923",)


def _geometry_blob(kind: int, coordinates: list[float], srs_id: int = 4326) -> bytes:
    """One GeoPackage geometry blob: header then well-known binary.

    The header is the spec's - magic, version, flags with a little-endian
    xy envelope, the srs id - and the payload is WKB. An envelope is included
    because a fixture a provider has to compute one for is a fixture that tests
    the provider's guesswork rather than the SDK.
    """
    xs = coordinates[0::2]
    ys = coordinates[1::2]
    envelope = struct.pack("<4d", min(xs), max(xs), min(ys), max(ys))
    header = struct.pack("<2sBBi", b"GP", 0, 0x03, srs_id) + envelope
    wkb = struct.pack("<BI", 1, kind)  # little-endian point/line string
    if kind == 1:
        wkb += struct.pack("<2d", *coordinates)
    else:
        wkb += struct.pack("<I", len(xs)) + struct.pack(
            f"<{len(coordinates)}d", *coordinates
        )
    return header + wkb


def write_geopackage(path: Path) -> Path:
    """Write the fixture GeoPackage and answer the path.

    The metadata tables are the specification's, byte for byte in column order:
    a GeoPackage GDAL opens has to answer ``gpkg_contents``,
    ``gpkg_geometry_columns`` and ``gpkg_spatial_ref_sys``, and the rows below
    are the smallest set that names all three tables and gives the two spatial
    ones an EPSG:4326 home.
    """
    _s = _CcState(path=path)
    for _p in (_cc_write_geopackage_p10,):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None
