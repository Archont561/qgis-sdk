"""The ``Features`` contract over the layers a ``NativeLayers`` opened."""

from __future__ import annotations

from qgis.core import (
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeature,
    QgsFeatureRequest,
    QgsRectangle,
    QgsVectorLayer,
)

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    ExpressionCheck,
    ExpressionOutcome,
    Feature,
    FeaturePage,
    FeatureQuery,
    QgisSdkLayerNotFoundError,
    QgisSdkUnsupportedCapabilityError,
)

from ._editing import NativeFeatureEditing
from ._geometry import encode

__all__ = ["NativeFeatures"]


def _page_phase1(layer, query, self, truncated, window):
    items = tuple(
        self._feature(layer, feature, query.encoding, query.with_geometry)
        for feature in window
    )
    cursor = str(window[-1].id()) if truncated and window else None
    return FeaturePage(items=items, truncated=truncated, next_cursor=cursor)


class NativeFeatures:
    """The ``Features`` contract over the layers a ``NativeLayers`` opened."""

    def __init__(self, layers, scope: ResourceScope) -> None:
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
        return _page_phase1(layer, query, self, truncated, window)

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
            geometry = encode(feature.geometry(), encoding, layer.crs().authid())
        return Feature(id=feature.id(), attributes=attributes, geometry=geometry)
