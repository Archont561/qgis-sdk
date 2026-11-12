"""PyQGIS-backed features, expressions and editing.

Native module: importing it needs a QGIS installation, so nothing on the pure
side may import it. It answers the ``Features`` contract with
``QgsFeatureRequest`` for paging and filtering, ``QgsExpression`` for the two
expression methods, and the layer's own edit buffer for sessions.

Four things are deliberate, and they are what the docs promise rather than what
QGIS could theoretically do:

*Paging continues from a feature id.* The cursor is the last id of the previous
page and it becomes a ``$id > cursor`` filter, so a client never re-reads a row
and never skips one. Rows are taken in the order the provider hands them back,
which OGR does in id order; a provider that shuffles its features is a paging
hazard this adapter does not paper over.

*Editing is the provider's, and so are its guarantees.* A session starts the
layer's edit buffer, ``commit`` calls ``commitChanges`` and reports what the
provider wrote. QGIS wraps a commit in a transaction only for the providers whose
data provider implements one; for the rest the commit is a sequence of writes.
``commit`` therefore reports ``committed`` and never claims atomicity, and a
failed commit is raised with the provider's message rather than rolled back
silently - rolling back a partial write is itself a provider capability.

*Expressions are evaluated by QGIS, in a prepared context.* ``check`` gives the
parser's verdict; ``evaluate`` gives a value or the evaluation error, so a page
can tell a syntax error from a null result.

*Nothing native crosses the boundary.* A ``QgsFeature``, a ``QgsGeometry`` and a
``QgsExpression`` all die here; what leaves is the SDK's models.
"""

from __future__ import annotations

from ._editing import NativeFeatureEditing
from ._features import NativeFeatures

__all__ = ["NativeFeatureEditing", "NativeFeatures"]
