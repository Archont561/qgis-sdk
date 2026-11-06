"""Author-readable behavior for the raster and the project services.

The scenarios live in ``features/raster_reads.feature`` and
``features/project_service.feature``; their steps are in ``service_steps.py``,
registered for every module through ``tests/conftest.py``. Two files rather than
one because a raster read and a project edit are two services a plugin meets
separately, even though both end up on the same project.
"""

from pytest_bdd import scenarios

scenarios("features/raster_reads.feature")
scenarios("features/project_service.feature")
