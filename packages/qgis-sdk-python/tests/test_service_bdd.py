"""Author-readable behavior for the raster, project and layout services.

The scenarios live in ``features/raster_reads.feature``,
``features/project_service.feature`` and ``features/layout_exports.feature``;
their steps are in ``service_steps.py``, registered for every module through
``tests/conftest.py``. Three files rather than one because a raster read, a
project edit and a print-layout export are three services a plugin meets
separately, even though all three end up on the same project.
"""

from pytest_bdd import scenarios

scenarios("features/raster_reads.feature")
scenarios("features/project_service.feature")
scenarios("features/layout_exports.feature")
