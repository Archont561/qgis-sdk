"""Features, their geometry and the values an expression returns.

decision-54 point 3 draws this boundary. A page reads *features*, not a
``QgsVectorLayer``: an id the provider assigned, the attribute values that layer
declares, and its geometry in one of three encodings. Nothing here carries a
native handle, a projection object or a path, so the same value is what the fake
layer, the native adapter and the wire all say.

Three choices are deliberate.

*Geometry crosses encoded, never as an object graph.* WKB is base64 in
``value``, WKT and GeoJSON are text. A page that wants to draw can hand GeoJSON
straight to a renderer; a page that wants to store can keep the WKB byte for
byte. The encoder is named in ``encoding`` so a reader never guesses.

*Paging is by the provider's feature id, ascending.* ``next_cursor`` is the last
id of the page, not an offset: a provider that reorders between two calls cannot
make a client skip a row, and the same query over the same data returns the same
pages.

*An expression outcome is a value or a message, never both.* ``valid`` says
whether the text parsed; a parsed expression that evaluated to a null value is
``valid`` with ``value`` null, which is a different answer from a syntax error.
"""

from __future__ import annotations

from ._expressions import EDIT_KINDS, EditOutcome, ExpressionCheck, ExpressionOutcome
from ._features import (
    DEFAULT_FEATURE_PAGE,
    MAX_FEATURE_PAGE,
    Feature,
    FeaturePage,
    FeatureQuery,
)
from ._geometry import GEOMETRY_ENCODINGS, GEOMETRY_TYPES, Geometry
from ._wire import (
    EDIT_OUTCOME,
    EXPRESSION_CHECK,
    EXPRESSION_OUTCOME,
    FEATURE,
    FEATURE_PAGE,
    FEATURE_QUERY,
    GEOMETRY,
)

__all__ = [
    "DEFAULT_FEATURE_PAGE",
    "EDIT_KINDS",
    "EDIT_OUTCOME",
    "EXPRESSION_CHECK",
    "EXPRESSION_OUTCOME",
    "FEATURE",
    "FEATURE_PAGE",
    "FEATURE_QUERY",
    "GEOMETRY",
    "GEOMETRY_ENCODINGS",
    "GEOMETRY_TYPES",
    "MAX_FEATURE_PAGE",
    "EditOutcome",
    "ExpressionCheck",
    "ExpressionOutcome",
    "Feature",
    "FeaturePage",
    "FeatureQuery",
    "Geometry",
]
