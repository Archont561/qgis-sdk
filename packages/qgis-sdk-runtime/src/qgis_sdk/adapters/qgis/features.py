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

import base64

from qgis.core import (
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsRectangle,
    QgsVectorLayer,
)

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    EditOutcome,
    ExpressionCheck,
    ExpressionOutcome,
    Feature,
    FeaturePage,
    FeatureQuery,
    Geometry,
    QgisSdkLayerNotFoundError,
    QgisSdkUnsupportedCapabilityError,
)

from .layers import NativeLayers

__all__ = ["NativeFeatureEditing", "NativeFeatures"]

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


def _geometry_type_code(geometry: QgsGeometry) -> int:
    """The flat WKB type code of a geometry, without Z/M/25D decorations.

    ``WkbType`` is a single enum whose Z, M and ZM variants are the flat code with
    a thousands digit, and whose legacy 25D variants set the high bit; a page
    reasons about "point" and "multipoint", so both decorations are dropped here.
    """
    return (int(geometry.wkbType()) & ~_WKB_25D) % 1000


def _vertex_count(geometry: QgsGeometry) -> int:
    """Every vertex of the geometry, parts included."""
    return int(geometry.constGet().vertexCount())


def _part_count(geometry: QgsGeometry) -> int:
    """Parts of the geometry: one for a single part, N for a collection."""
    return int(geometry.constGet().partCount())


def _encode(geometry: QgsGeometry, encoding: str, crs: str | None) -> Geometry:
    """Encode one QGIS geometry in the encoding the caller asked for."""
    if geometry.isNull() or geometry.isEmpty():
        value = ""
        if encoding == "wkb" and not geometry.isNull():
            value = base64.b64encode(bytes(geometry.asWkb())).decode("ascii")
        return Geometry(
            encoding=encoding,
            value=value,
            geometry_type="none" if geometry.isNull() else _name(geometry),
            crs=crs,
            part_count=_part_count(geometry),
            is_empty=not geometry.isNull(),
        )
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
        geometry_type=_name(geometry),
        crs=crs,
        part_count=_part_count(geometry),
        vertex_count=_vertex_count(geometry),
    )


def _name(geometry: QgsGeometry) -> str:
    return _GEOMETRY_NAMES.get(_geometry_type_code(geometry), "geometrycollection")


def _decode(geometry: Geometry) -> QgsGeometry:
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


class NativeFeatures:
    """The ``Features`` contract over the layers a ``NativeLayers`` opened."""

    def __init__(self, layers: NativeLayers, scope: ResourceScope) -> None:
        self._layers = layers
        self._scope = scope
        self._sessions: dict[str, NativeFeatureEditing] = {}

    # -- reading ------------------------------------------------------------

    def page(self, layer_id: str, query: FeatureQuery) -> FeaturePage:
        """Read one page with the provider doing the filtering."""
        self._scope.ensure_open()
        layer = self._require(layer_id)
        request = QgsFeatureRequest()
        # One row more than asked for is how "is there another page" is answered
        # without counting the whole layer.
        request.setLimit(query.limit + 1)
        conditions: list[str] = []
        if query.cursor is not None:
            conditions.append(f"$id > {int(query.cursor)}")
        if query.expression:
            conditions.append(f"({query.expression})")
        if conditions:
            request.setFilterExpression(" AND ".join(conditions))
        elif query.ids is not None:
            # A plain list of ints is what SIP accepts for ``QgsFeatureIds``,
            # which is a typedef the bindings do not export as a name.
            request.setFilterFids(list(query.ids))
        if query.bbox is not None:
            request.setFilterRect(
                QgsRectangle(query.bbox[0], query.bbox[1], query.bbox[2], query.bbox[3])
            )
        rows = list(layer.getFeatures(request))
        truncated = len(rows) > query.limit
        window = rows[: query.limit]
        items = tuple(
            self._feature(layer, feature, query.encoding, query.with_geometry)
            for feature in window
        )
        cursor = str(window[-1].id()) if truncated and window else None
        return FeaturePage(items=items, truncated=truncated, next_cursor=cursor)

    def feature(
        self, layer_id: str, feature_id: int, *, encoding: str = "wkb"
    ) -> Feature:
        """Read one feature by id."""
        self._scope.ensure_open()
        layer = self._require(layer_id)
        for feature in layer.getFeatures(QgsFeatureRequest(feature_id)):
            return self._feature(layer, feature, encoding, True)
        raise QgisSdkLayerNotFoundError(f"{layer_id}#{feature_id}")

    def evaluate(
        self,
        text: str,
        *,
        layer_id: str | None = None,
        feature_id: int | None = None,
    ) -> ExpressionOutcome:
        """Evaluate one expression with QGIS's own parser and context."""
        self._scope.ensure_open()
        expression = QgsExpression(text)
        if expression.hasParserError():
            return ExpressionOutcome(
                valid=False, message=expression.parserErrorString()
            )
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
        layer = self._require(layer_id) if layer_id is not None else None
        if layer is not None:
            context.appendScope(QgsExpressionContextUtils.layerScope(layer))
            if feature_id is not None:
                for feature in layer.getFeatures(QgsFeatureRequest(feature_id)):
                    context.setFeature(feature)
                    break
                else:
                    raise QgisSdkLayerNotFoundError(f"{layer_id}#{feature_id}")
        expression.prepare(context)
        value = expression.evaluate(context)
        if expression.hasEvalError():
            return ExpressionOutcome(valid=False, message=expression.evalErrorString())
        return ExpressionOutcome(valid=True, value=value)

    def check(self, text: str, *, layer_id: str | None = None) -> ExpressionCheck:
        """Parse an expression without evaluating it."""
        self._scope.ensure_open()
        expression = QgsExpression(text)
        if expression.hasParserError():
            return ExpressionCheck(valid=False, message=expression.parserErrorString())
        columns: tuple[str, ...] = ()
        if layer_id is not None:
            layer = self._require(layer_id)
            names = {field.name() for field in layer.fields()}
            columns = tuple(
                name for name in expression.referencedColumns() if name in names
            )
        return ExpressionCheck(valid=True, referenced_columns=columns)

    # -- editing ------------------------------------------------------------

    def begin_edit(self, layer_id: str) -> NativeFeatureEditing:
        """Start the layer's edit buffer as a session this scope owns.

        A layer already being edited is a second session over the same buffer:
        the SDK returns the existing session instead of starting a second one,
        because two sessions committing one buffer is a race the caller cannot
        see. The session id is stable per layer for exactly that reason.
        """
        self._scope.ensure_open()
        layer = self._require(layer_id)
        if not layer.isEditable() and not layer.startEditing():
            provider = layer.dataProvider()
            raise QgisSdkUnsupportedCapabilityError(
                f"layer {layer_id!r} cannot be edited "
                f"(provider {provider.name() if provider is not None else 'unknown'})"
            )
        session = self._sessions.get(layer_id)
        if session is not None and not session.closed:
            return session
        session = NativeFeatureEditing(layer_id, layer, self._scope)
        self._sessions[layer_id] = session
        self._scope.on_close(session.close)
        return session

    # -- internals ----------------------------------------------------------

    def _require(self, layer_id: str | None) -> QgsVectorLayer:
        return self._layers._qgs_layer(str(layer_id))

    def _feature(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        encoding: str,
        with_geometry: bool,
    ) -> Feature:
        names = [field.name() for field in layer.fields()]
        attributes = {
            name: feature[name] for name in names if feature[name] is not None
        }
        geometry = None
        if with_geometry:
            geometry = _encode(feature.geometry(), encoding, layer.crs().authid())
        return Feature(id=feature.id(), attributes=attributes, geometry=geometry)


class NativeFeatureEditing:
    """One layer's edit buffer, as the view's session.

    ``commit`` reports what the provider wrote and whether it committed; it does
    not claim the write was atomic, because most providers do not promise that.
    ``rollback`` discards the buffer and leaves the session open on a fresh
    buffer, and ``close`` ends it with whatever the buffer holds discarded -
    which is what a view closing mid-edit must do.
    """

    def __init__(
        self, layer_id: str, layer: QgsVectorLayer, scope: ResourceScope
    ) -> None:
        self._layer_id = layer_id
        self._layer = layer
        self._scope = scope
        self._closed = False
        self._session_id = f"edit-{layer_id}"

    @property
    def id(self) -> str:
        return self._session_id

    @property
    def layer_id(self) -> str:
        return self._layer_id

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def pending(self) -> int:
        buffer = self._layer.editBuffer()
        if buffer is None:
            return 0
        return (
            len(buffer.addedFeatures())
            + len(buffer.changedAttributeValues())
            + len(buffer.changedGeometries())
            + len(buffer.deletedFeatureIds())
        )

    def add(
        self, attributes: dict[str, object], geometry: Geometry | None = None
    ) -> int:
        self._ensure_open()
        feature = QgsFeature(self._layer.fields())
        for name, value in attributes.items():
            if self._layer.fields().indexOf(name) < 0:
                raise QgisSdkUnsupportedCapabilityError(
                    f"layer {self._layer_id!r} has no field {name!r}"
                )
            feature[name] = value
        if geometry is not None:
            feature.setGeometry(_decode(geometry))
        if not self._layer.addFeature(feature):
            raise QgisSdkUnsupportedCapabilityError(
                f"layer {self._layer_id!r} refused the new feature"
            )
        return feature.id()

    def update(
        self,
        feature_id: int,
        attributes: dict[str, object] | None = None,
        geometry: Geometry | None = None,
    ) -> None:
        self._ensure_open()
        feature = self._require(feature_id)
        for name, value in (attributes or {}).items():
            if self._layer.fields().indexOf(name) < 0:
                raise QgisSdkUnsupportedCapabilityError(
                    f"layer {self._layer_id!r} has no field {name!r}"
                )
            feature[name] = value
        if geometry is not None:
            feature.setGeometry(_decode(geometry))
        if not self._layer.updateFeature(feature):
            raise QgisSdkUnsupportedCapabilityError(
                f"layer {self._layer_id!r} refused the change to feature {feature_id}"
            )

    def delete(self, feature_id: int) -> None:
        self._ensure_open()
        if not self._layer.deleteFeature(feature_id):
            raise QgisSdkLayerNotFoundError(f"{self._layer_id}#{feature_id}")

    def commit(self) -> EditOutcome:
        """Commit the buffer; a provider that cannot commit is reported, not hidden."""
        self._ensure_open()
        buffer = self._layer.editBuffer()
        added = (
            tuple(sorted(int(fid) for fid in buffer.addedFeatures()))
            if buffer is not None
            else ()
        )
        edited = 0
        if buffer is not None:
            edited = len(buffer.changedAttributeValues()) + len(
                buffer.changedGeometries()
            )
        deleted = len(buffer.deletedFeatureIds()) if buffer is not None else 0
        if not self._layer.commitChanges():
            message = "; ".join(self._layer.commitErrors()) or "the provider refused"
            raise QgisSdkUnsupportedCapabilityError(
                f"layer {self._layer_id!r} could not commit: {message}"
            )
        return EditOutcome(
            applied=len(added) + edited + deleted,
            feature_ids=added,
            committed=True,
        )

    def rollback(self) -> int:
        if self._closed:
            return 0
        pending = self.pending
        self._layer.rollBack()
        self._layer.startEditing()
        return pending

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._layer.rollBack()

    def _ensure_open(self) -> None:
        self._scope.ensure_open()
        if self._closed:
            raise QgisSdkUnsupportedCapabilityError(
                f"editing session {self._session_id!r} is closed"
            )

    def _require(self, feature_id: int) -> QgsFeature:
        for feature in self._layer.getFeatures(QgsFeatureRequest(feature_id)):
            return feature
        raise QgisSdkLayerNotFoundError(f"{self._layer_id}#{feature_id}")
