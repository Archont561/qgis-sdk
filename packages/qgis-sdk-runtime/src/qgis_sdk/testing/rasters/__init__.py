"""A ``Rasters`` backend over bands a test declares, with no GDAL behind it.

The fake exists for the same reason :class:`~qgis_sdk.testing.fakes.FakeLayers`
does: so a workflow reads a raster in a pure test, and so the contract suite can
hold this backend and the native one to identical expectations. It is not a
raster engine, and three limits are deliberate rather than accidental.

*Statistics are declared, not computed.* A fake that computed a mean would need
a pixel grid and an arithmetic that agreed with GDAL to the last bit, which is a
second implementation and not a test double. A test declares the numbers a
fixture would produce, and the contract test asserts both backends answer them.

*Sampling answers the declared value for any point inside the box.* There is no
grid, so a point in the extent gets the band's declared value and a point
outside gets ``None``, which is exactly the two answers a caller distinguishes.

*Reprojection is refused by name.* The fake has no CRS database, so a point
whose ``crs`` differs from the raster's raises instead of silently treating two
different coordinate systems as one; a caller that wants a real transform runs
the native backend.

Export is real: the declared source file is copied under the shared policy, so
refusal, staging, commit and cleanup are the same code path the native adapter
runs.
"""

from __future__ import annotations

from ._rasters import FakeRasters

__all__ = ["FakeRasters"]
