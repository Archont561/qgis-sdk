"""The three fixture files TASK-91's native half opens, built rather than committed.

A mesh is text - the checked-in ``fixtures/reference/lagoon.2dm`` - and an
annotation layer is created rather than opened, so both sides of that contract
read something a reviewer can see. The other three kinds are containers:

* a point cloud is a LAS file, a 227-byte header followed by fixed-width point
  records;
* a vector tile source is an MBTiles database, which is SQLite;
* a 3D tiled scene is a ``tileset.json`` beside the tiles it names.

The last one is JSON, but the first two are binary, and committing a blob nobody
can read in a diff is how a fixture rots into "that file, whatever it is". They
are written here instead: ``struct`` and ``sqlite3`` are standard library, the
files are deterministic, and the suite's own tests read them back field by field
(``test_layer_kinds.py``), so a header PDAL would refuse fails the *pure* lane
rather than only the opt-in native one.

The numbers are the smallest a provider accepts, not the smallest a file can be:
a LAS header whose declared extent disagrees with its points, or an MBTiles
database with no ``format``, is a file QGIS refuses, and a fixture that a
provider refuses proves nothing about the SDK.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
import struct
from pathlib import Path


def _write_point_cloud_facts1(header, path, points):
    records = b"".join(
        struct.pack(
            "<3iHBBbBH",
            round(x / LAS_SCALE),
            round(y / LAS_SCALE),
            round(z / LAS_SCALE),
            0,  # intensity
            0,  # return number, number of returns, scan direction, edge of flight
            0,  # classification: never classified
            0,  # scan angle rank
            0,  # user data
            0,  # point source id
        )
        for x, y, z in points
    )
    path.write_bytes(header + records)
    return path


# -- LAS 1.2, point data format 0 --------------------------------------------
#: The header of a LAS 1.2 file is exactly this long, and a file with no VLRs
#: puts its first point record right after it.
LAS_HEADER_SIZE = 227
#: Point data format 0 is 20 bytes: three 32-bit integers and seven small fields.
LAS_POINT_RECORD_LENGTH = 20
#: A hundredth of a metre. LAS stores coordinates as integers plus this scale, so
#: the numbers below survive the round trip exactly.
LAS_SCALE = 0.01
#: ``(x, y, z)`` metres, with no projection: a survey flown before anyone
#: assigned one, which is why the description says "no CRS" instead of borrowing
#: the project's.
POINT_CLOUD_POINTS = ((21.0, 52.0, 10.0), (21.1, 52.1, 12.5), (21.2, 52.2, 15.0))
POINT_CLOUD_NAME = "survey"

# -- MBTiles ------------------------------------------------------------------
#: One gzipped Mapbox vector tile with no layers in it. An empty protobuf message
#: is a valid MVT tile, and the contract opens a layer - it never renders one -
#: so the tile only has to parse.
EMPTY_VECTOR_TILE = gzip.compress(b"", mtime=0)
VECTOR_TILE_NAME = "basemap"
VECTOR_TILE_MIN_ZOOM = 0
VECTOR_TILE_MAX_ZOOM = 2

# -- 3D Tiles -----------------------------------------------------------------
#: ``west, south, east, north, minimum height, maximum height`` in degrees and
#: metres - the same box the three reference points cover, so the scene sits
#: where the rest of the fixtures do.
TILED_SCENE_REGION = (21.0, 52.0, 21.2, 52.2, 0.0, 60.0)


def write_point_cloud(
    path: Path, *, points: tuple[tuple[float, float, float], ...] = POINT_CLOUD_POINTS
) -> Path:
    """Write a LAS 1.2 point cloud of ``points`` and answer the path.

    ``global_encoding`` is 0 and there are no variable length records, because
    a CRS would live in one: the point cloud this fixture models has none, and a
    description that invented one would be wrong about a layer a page draws.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    xs = [x for x, _y, _z in points]
    ys = [y for _x, y, _z in points]
    zs = [z for _x, _y, z in points]
    header = struct.pack(
        "<4sHHIHH8sBB32s32sHHHIIBHI5I3d3d6d",
        b"LASF",
        0,  # file source id
        0,  # global encoding
        0,  # project id, GUID data 1
        0,  # GUID data 2
        0,  # GUID data 3
        bytes(8),  # GUID data 4
        1,  # version major
        2,  # version minor
        b"qgis-sdk".ljust(32, b"\0"),
        b"qgis-sdk fixtures".ljust(32, b"\0"),
        1,  # file creation day of year
        2026,  # file creation year
        LAS_HEADER_SIZE,
        LAS_HEADER_SIZE,  # offset to point data: no VLRs
        0,  # number of variable length records
        0,  # point data format id
        LAS_POINT_RECORD_LENGTH,
        len(points),  # legacy number of point records
        len(points),
        0,
        0,
        0,
        0,  # legacy number of points by return
        LAS_SCALE,
        LAS_SCALE,
        LAS_SCALE,
        0.0,
        0.0,
        0.0,  # x, y and z offsets
        max(xs),
        min(xs),
        max(ys),
        min(ys),
        max(zs),
        min(zs),
    )
    assert len(header) == LAS_HEADER_SIZE, "the LAS header layout moved"
    return _write_point_cloud_facts1(header, path, points)


def write_vector_tiles(
    path: Path,
    *,
    name: str = VECTOR_TILE_NAME,
    min_zoom: int = VECTOR_TILE_MIN_ZOOM,
    max_zoom: int = VECTOR_TILE_MAX_ZOOM,
) -> Path:
    """Write an MBTiles database holding one empty tile per zoom and answer the path.

    The four tables and the metadata keys are the MBTiles specification's, and
    ``format = pbf`` is what makes a tile source a *vector* tile source rather
    than a raster one.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as database:
        database.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
        database.execute(
            "CREATE TABLE tiles ("
            "zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, "
            "tile_data BLOB)"
        )
        database.execute(
            "CREATE UNIQUE INDEX tile_index ON tiles "
            "(zoom_level, tile_column, tile_row)"
        )
        database.executemany(
            "INSERT INTO metadata (name, value) VALUES (?, ?)",
            (
                ("name", name),
                ("format", "pbf"),
                ("type", "baselayer"),
                ("version", "1"),
                ("description", "qgis-sdk layer-kind fixture"),
                ("bounds", "-180,-85.05112877980659,180,85.05112877980659"),
                ("center", "0,0,0"),
                ("minzoom", str(min_zoom)),
                ("maxzoom", str(max_zoom)),
            ),
        )
        database.executemany(
            "INSERT INTO tiles VALUES (?, ?, ?, ?)",
            ((zoom, 0, 0, EMPTY_VECTOR_TILE) for zoom in range(min_zoom, max_zoom + 1)),
        )
    return path


def write_tiled_scene(
    path: Path, *, region: tuple[float, ...] = TILED_SCENE_REGION
) -> Path:
    """Write a 3D Tiles ``tileset.json`` covering ``region`` and answer the path.

    The root tile carries a bounding volume and no content: 3D Tiles allows a
    tile with nothing to draw, and opening a scene builds the index from the
    tileset rather than fetching a tile, so a tileset with no ``content`` is the
    smallest file that proves the open.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tileset = {
        "asset": {"version": "1.0"},
        "geometricError": 1000.0,
        "root": {
            "boundingVolume": {"region": list(region)},
            "geometricError": 0,
            "refine": "ADD",
        },
    }
    path.write_text(json.dumps(tileset, indent=2) + "\n", encoding="utf-8")
    return path
