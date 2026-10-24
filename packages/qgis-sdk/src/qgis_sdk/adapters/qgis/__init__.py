"""PyQGIS-backed service adapters for the curated pure contracts.

Importing this package needs a QGIS installation. It is deliberately absent from
the eager pure import surface: ``qgis_sdk.adapters`` does not re-export it, and
``tests/test_pure_imports.py`` imports the other adapters with QGIS blocked.

The adapters in this package implement the same ``qgis_sdk.services`` contracts
as the in-memory doubles, and the contract suite in ``tests/services`` runs both
against one set of tests.
"""

from .layers import NativeLayers
from .project import NativeProject

__all__ = ["NativeLayers", "NativeProject"]
