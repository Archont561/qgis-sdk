"""The ``Features`` protocol over :class:`FakeLayer` values."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict, Unpack

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    ExpressionCheck,
    ExpressionOutcome,
    Feature,
    FeaturePage,
    FeatureQuery,
    Geometry,
    QgisSdkLayerNotFoundError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.testing.expressions import (
    ExpressionSubset,
    literal_token,
    literal_value,
)

from ._layer import FakeLayer, point_coordinates
from ._session import FakeEditingSession

__all__ = ["FakeFeatures"]


class _FakeFeaturesMixin1:
    # -- declaring data -----------------------------------------------------

    def declare(self, layer_id: str, **options: Unpack[_DeclareOptions1]) -> FakeLayer:
        """Create a layer the service answers for, and return it for inspection.

        A row's third item is one :class:`Geometry` or a mapping of encodings to
        geometries - ``{"wkt": ..., "geojson": ...}`` - which is how a test
        declares the encodings it will read back.
        """
        values = _DeclareValues1(**options)
        layer = FakeLayer(
            fields=tuple(values.fields), editable=values.editable, atomic=values.atomic
        )
        for feature_id, attributes, geometry in values.rows:
            layer.rows[feature_id] = dict(attributes)
            if isinstance(geometry, Geometry):
                layer.geometries[feature_id] = {geometry.encoding: geometry}
            elif geometry is not None:
                layer.geometries[feature_id] = dict(geometry)
        self._layers[layer_id] = layer
        self._next_id[layer_id] = max(layer.rows, default=0) + 1
        return layer

    def layer(self, layer_id: str) -> FakeLayer:
        """Return the declared layer, or refuse by name."""
        self._scope.ensure_open()
        layer = self._layers.get(layer_id)
        if layer is None:
            raise QgisSdkLayerNotFoundError(layer_id)
        return layer

    # -- reading ------------------------------------------------------------

    def page(self, layer_id: str, query: FeatureQuery) -> FeaturePage:
        """Return one page ordered by feature id, filtered by the provider."""
        layer = self.layer(layer_id)
        matching = [
            feature_id
            for feature_id in sorted(layer.rows)
            if self._matches(layer, feature_id, query)
        ]
        start = query.start
        if start is not None:
            matching = [feature_id for feature_id in matching if feature_id > start]
        window = matching[: query.limit]
        truncated = len(matching) > len(window)
        items = tuple(
            self._feature(layer, feature_id, query.encoding, query.with_geometry)
            for feature_id in window
        )
        return FeaturePage(
            items=items,
            truncated=truncated,
            next_cursor=str(window[-1]) if truncated and window else None,
        )

    def feature(
        self, layer_id: str, feature_id: int, *, encoding: str = "wkb"
    ) -> Feature:
        """Return one feature, or refuse by its id."""
        layer = self.layer(layer_id)
        if feature_id not in layer.rows:
            raise QgisSdkLayerNotFoundError(f"{layer_id}#{feature_id}")
        return self._feature(layer, feature_id, encoding, True)

    def _literal(self, text: str, **context: Any) -> ExpressionOutcome:
        """A literal as an outcome; one the subset cannot carry is a refusal.

        Both callers of ``_literal_value`` answer the same way - a value when it
        is one, a message when it is not - so the answer is written once.
        """
        try:
            return ExpressionOutcome(
                valid=True, value=self._literal_value(text, **context)
            )
        except QgisSdkUnsupportedCapabilityError as error:
            return ExpressionOutcome(valid=False, message=str(error))

    def evaluate(
        self,
        text: str,
        *,
        layer_id: str | None = None,
        feature_id: int | None = None,
    ) -> ExpressionOutcome:
        """Evaluate a comparison, a field name or a literal against one row."""
        if layer_id is None:
            return self._literal(text)
        layer = self.layer(layer_id)
        row: Mapping[str, Any] = {}
        if feature_id is not None:
            if feature_id not in layer.rows:
                raise QgisSdkLayerNotFoundError(f"{layer_id}#{feature_id}")
            row = layer.rows[feature_id]
        try:
            parsed = ExpressionSubset.parse(text, layer.fields)
        except QgisSdkUnsupportedCapabilityError:
            # A bare field name is a value, not a comparison.
            return self._literal(text, row=row, fields=layer.fields)
        if feature_id is None:
            # Nothing to compare against: the expression parses, and its value
            # is the expression itself, which is what a "does it parse" caller
            # asked for.
            return ExpressionOutcome(valid=True, value=text)
        return ExpressionOutcome(valid=True, value=parsed.matches(row))

    def check(self, text: str, *, layer_id: str | None = None) -> ExpressionCheck:
        """Parse without running, reporting the columns the expression names."""
        fields: tuple[str, ...] = ()
        if layer_id is not None:
            fields = self.layer(layer_id).fields
        try:
            if layer_id is None:
                self._literal_value(text)
                return ExpressionCheck(valid=True)
            parsed = ExpressionSubset.parse(text, fields)
        except QgisSdkUnsupportedCapabilityError as error:
            return ExpressionCheck(valid=False, message=str(error))
        return ExpressionCheck(
            valid=True,
            referenced_columns=tuple(
                dict.fromkeys(clause[0] for clause in parsed.clauses)
            ),
        )

    # -- editing ------------------------------------------------------------

    def begin_edit(self, layer_id: str) -> FakeEditingSession:
        """Open an editing session, or refuse a layer that cannot be edited.

        A layer already being edited returns the open session rather than a
        second one: the native adapter does the same, because two sessions
        committing one provider buffer is a race the caller cannot see (the
        layer, not the call, owns the buffer).
        """
        layer = self.layer(layer_id)
        if not layer.editable:
            raise QgisSdkUnsupportedCapabilityError(
                f"layer {layer_id!r} is read-only; the provider cannot edit it"
            )
        for session in self._sessions.values():
            if session.layer_id == layer_id and not session.closed:
                return session
        self._next_session += 1
        session = FakeEditingSession(
            session_id=f"edit-{self._next_session}",
            layer_id=layer_id,
            layer=layer,
            assign=lambda: self._assign(layer_id),
            on_close=self._sessions.pop,
        )
        self._sessions[session.id] = session
        return session

    def session(self, session_id: str) -> FakeEditingSession:
        """Return an open session, or refuse by id."""
        session = self._sessions.get(session_id)
        if session is None:
            raise QgisSdkLayerNotFoundError(f"editing session {session_id!r}")
        return session

    # -- internals ----------------------------------------------------------

    def _assign(self, layer_id: str) -> int:
        feature_id = self._next_id[layer_id]
        self._next_id[layer_id] = feature_id + 1
        return feature_id

    def _matches(self, layer: FakeLayer, feature_id: int, query: FeatureQuery) -> bool:
        if query.ids is not None and feature_id not in query.ids:
            return False
        geometries = layer.geometries.get(feature_id) or {}
        if query.bbox is not None:
            # The fake only checks the point case, and only from WKT: a bbox
            # over a real geometry is the provider's job, and guessing it here
            # would let a test pass for a selection QGIS would answer
            # differently.
            point = geometries.get("wkt")
            coordinates = point_coordinates(point) if point is not None else None
            if coordinates is None:
                return False
            min_x, min_y, max_x, max_y = query.bbox
            if not (
                min_x <= coordinates[0] <= max_x and min_y <= coordinates[1] <= max_y
            ):
                return False
        if query.expression is not None:
            parsed = ExpressionSubset.parse(query.expression, layer.fields)
            return parsed.matches(layer.rows[feature_id])
        return True


class _FakeFeaturesMixin2:
    def _feature(
        self, layer: FakeLayer, feature_id: int, encoding: str, with_geometry: bool
    ) -> Feature:
        geometry: Geometry | None = None
        if with_geometry:
            stored = (layer.geometries.get(feature_id) or {}).get(encoding)
            if stored is None and layer.geometries.get(feature_id):
                raise QgisSdkUnsupportedCapabilityError(
                    f"the fake layer has no {encoding!r} geometry for feature "
                    f"{feature_id}; it declared "
                    f"{sorted(layer.geometries[feature_id])}"
                )
            # A row with no shape of its own still reports one: `None` on a
            # `Feature` means the page did not ask for a geometry, and reading a
            # row without one as "not requested" would answer a question nobody
            # asked. ``geometry_type`` "none" is the missing case, which is a
            # different fact from an empty geometry (doc-12).
            geometry = stored or Geometry(
                encoding=encoding, value="", geometry_type="none"
            )
        return Feature(
            id=feature_id,
            attributes=dict(layer.rows[feature_id]),
            geometry=geometry,
        )

    def _literal_value(
        self,
        text: str,
        *,
        row: Mapping[str, Any] | None = None,
        fields: Sequence[str] = (),
    ) -> Any:
        token = literal_token(text)
        if token.kind == "string" and token.value.startswith('"') and row is not None:
            # In an expression a double-quoted token names a column while a
            # single-quoted one is a string; the fake keeps the distinction,
            # because a page that confuses them reads a value that is not there.
            token = literal_token(token.value[1:-1])
        if token.kind == "name" and row is not None:
            if token.value not in fields:
                raise QgisSdkUnsupportedCapabilityError(
                    f"the layer has no field {token.value!r}; fields are {list(fields)}"
                )
            return row.get(token.value)
        return literal_value(token)

    def _release(self) -> None:
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()
        self._layers.clear()


class FakeFeatures(_FakeFeaturesMixin1, _FakeFeaturesMixin2):
    """The ``Features`` protocol over :class:`FakeLayer` values.

    Layers are declared by the test with :meth:`declare`, which is also how a
    non-editable layer (a raster source, a read-only file) is modelled: editing
    it raises by name, exactly as the native adapter does.
    """

    def __init__(self, scope: ResourceScope) -> None:
        self._scope = scope
        self._layers: dict[str, FakeLayer] = {}
        self._sessions: dict[str, FakeEditingSession] = {}
        self._next_id: dict[str, int] = {}
        self._next_session = 0
        scope.on_close(self._release)


class _DeclareOptions1(TypedDict, total=False):
    fields: Sequence[str]
    rows: Iterable[tuple[int, Mapping[str, Any], Any]]
    editable: bool
    atomic: bool


@dataclass(frozen=True, slots=True)
class _DeclareValues1:
    fields: Sequence[str]
    rows: Iterable[tuple[int, Mapping[str, Any], Any]] = ()
    editable: bool = True
    atomic: bool = True
