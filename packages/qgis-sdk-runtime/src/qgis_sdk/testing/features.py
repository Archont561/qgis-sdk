"""An in-memory ``Features`` backend: pages, filters, expressions and editing.

The fake exists so the contract can be exercised without QGIS: the same page
shapes, the same deterministic ordering, the same refusals. It is honest about
its bounds - the expression subset in :mod:`qgis_sdk.testing.expressions` is not
``QgsExpression`` - and it makes the parts of editing the native adapter cannot
guarantee explicit, because a fake is the one place where a test can say which
guarantee it is asserting.

Editing here behaves like the providers this SDK supports best: a buffer that is
written on commit, an id the fake assigns for an add, and a rollback that
discards. ``atomic=False`` models the providers that write row by row, so a test
can prove the outcome says so instead of implying a transaction the provider does
not have.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    EditOutcome,
    ExpressionCheck,
    ExpressionOutcome,
    Feature,
    FeaturePage,
    FeatureQuery,
    Geometry,
    QgisSdkFeatureEditError,
    QgisSdkLayerNotFoundError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.testing.expressions import (
    ExpressionSubset,
    literal_token,
    literal_value,
)

__all__ = ["FakeFeatures", "FakeLayer"]


def _point_coordinates(geometry: Geometry | None) -> tuple[float, float] | None:
    """Read the two numbers of a WKT point, or ``None`` for anything else."""
    if geometry is None or geometry.geometry_type != "point":
        return None
    match = _WKT_POINT.match(geometry.value)
    if match is None:
        return None
    return float(match.group("x")), float(match.group("y"))


_WKT_POINT = re.compile(
    r"\s*POINT\s*\(\s*(?P<x>-?\d+(?:\.\d+)?)\s+(?P<y>-?\d+(?:\.\d+)?)\s*\)\s*",
    re.IGNORECASE,
)


@dataclass
class FakeLayer:
    """One layer's rows: the ids, their attributes and their geometries.

    ``geometries`` is keyed by feature id and then by encoding. The fake does
    not convert between encodings - that is a geometry engine's job, and a fake
    that approximated it would let a round-trip test pass for a conversion QGIS
    would have refused - so a test declares the encodings it wants to read back
    and asking for another one is refused by name.
    """

    fields: tuple[str, ...]
    rows: dict[int, dict[str, Any]] = field(default_factory=dict)
    geometries: dict[int, dict[str, Geometry]] = field(default_factory=dict)
    editable: bool = True
    #: ``False`` models a provider that writes row by row, so a commit that
    #: fails halfway leaves the rows it already wrote behind (decision-54).
    atomic: bool = True
    #: Bumped on every commit; a session that began earlier sees it change.
    revision: int = 0


class FakeFeatures:
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

    # -- declaring data -----------------------------------------------------

    def declare(
        self,
        layer_id: str,
        *,
        fields: Sequence[str],
        rows: Iterable[tuple[int, Mapping[str, Any], Any]] = (),
        editable: bool = True,
        atomic: bool = True,
    ) -> FakeLayer:
        """Create a layer the service answers for, and return it for inspection.

        A row's third item is one :class:`Geometry` or a mapping of encodings to
        geometries - ``{"wkt": ..., "geojson": ...}`` - which is how a test
        declares the encodings it will read back.
        """
        layer = FakeLayer(fields=tuple(fields), editable=editable, atomic=atomic)
        for feature_id, attributes, geometry in rows:
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

    def evaluate(
        self,
        text: str,
        *,
        layer_id: str | None = None,
        feature_id: int | None = None,
    ) -> ExpressionOutcome:
        """Evaluate a comparison, a field name or a literal against one row."""
        if layer_id is None:
            try:
                return ExpressionOutcome(valid=True, value=self._literal_value(text))
            except QgisSdkUnsupportedCapabilityError as error:
                return ExpressionOutcome(valid=False, message=str(error))
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
            try:
                return ExpressionOutcome(
                    valid=True,
                    value=self._literal_value(text, row=row, fields=layer.fields),
                )
            except QgisSdkUnsupportedCapabilityError as error:
                return ExpressionOutcome(valid=False, message=str(error))
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
            coordinates = _point_coordinates(point) if point is not None else None
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
            geometry = stored
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


@dataclass
class FakeEditingSession:
    """A buffered edit session over one :class:`FakeLayer`."""

    session_id: str
    layer_id: str
    layer: FakeLayer
    assign: Any
    on_close: Any
    added: dict[int, tuple[dict[str, Any], Geometry | None]] = field(
        default_factory=dict
    )
    updated: dict[int, tuple[dict[str, Any], Geometry | None]] = field(
        default_factory=dict
    )
    deleted: set[int] = field(default_factory=set)
    closed: bool = False
    #: The message the next commit raises, which is how a test models a
    #: provider that refuses a write halfway (``atomic=False``).
    failure: str | None = None

    @property
    def id(self) -> str:
        return self.session_id

    @property
    def pending(self) -> int:
        return len(self.added) + len(self.updated) + len(self.deleted)

    def add(
        self, attributes: dict[str, object], geometry: Geometry | None = None
    ) -> int:
        self._ensure_open()
        unknown = set(attributes) - set(self.layer.fields)
        if unknown:
            raise QgisSdkUnsupportedCapabilityError(
                f"the layer has no field {min(unknown)!r}"
            )
        feature_id = self.assign()
        self.added[feature_id] = (dict(attributes), geometry)
        return feature_id

    def update(
        self,
        feature_id: int,
        attributes: dict[str, object] | None = None,
        geometry: Geometry | None = None,
    ) -> None:
        self._ensure_open()
        self._require(feature_id)
        merged_attributes, merged_geometry = self.updated.get(feature_id, ({}, None))
        attributes = {**merged_attributes, **(attributes or {})}
        unknown = set(attributes) - set(self.layer.fields)
        if unknown:
            raise QgisSdkUnsupportedCapabilityError(
                f"the layer has no field {min(unknown)!r}"
            )
        self.updated[feature_id] = (
            attributes,
            geometry if geometry is not None else merged_geometry,
        )

    def delete(self, feature_id: int) -> None:
        self._ensure_open()
        self._require(feature_id)
        self.deleted.add(feature_id)

    def fail_next_commit(self, message: str) -> None:
        """Make the next commit raise ``message``, as a refusing provider does."""
        self.failure = message

    def commit(self) -> EditOutcome:
        """Write the buffer, in the order adds, updates, deletes."""
        self._ensure_open()
        if self.failure is not None:
            message, self.failure = self.failure, None
            raise QgisSdkFeatureEditError(
                f"the provider rejected the commit: {message}"
            )
        assigned: list[int] = []
        for feature_id, (attributes, geometry) in self.added.items():
            self.layer.rows[feature_id] = attributes
            if geometry is not None:
                self.layer.geometries[feature_id] = geometry
            assigned.append(feature_id)
        for feature_id, (attributes, geometry) in self.updated.items():
            self.layer.rows[feature_id].update(attributes)
            if geometry is not None:
                self.layer.geometries[feature_id] = geometry
        for feature_id in self.deleted:
            self.layer.rows.pop(feature_id, None)
            self.layer.geometries.pop(feature_id, None)
        applied = len(assigned) + len(self.updated) + len(self.deleted)
        self.layer.revision += 1
        self.added.clear()
        self.updated.clear()
        self.deleted.clear()
        return EditOutcome(applied=applied, feature_ids=tuple(assigned), committed=True)

    def rollback(self) -> int:
        dropped = self.pending
        self.added.clear()
        self.updated.clear()
        self.deleted.clear()
        return dropped

    def close(self) -> None:
        if self.closed:
            return
        self.rollback()
        self.closed = True
        self.on_close(self.session_id, None)

    def _ensure_open(self) -> None:
        if self.closed:
            raise QgisSdkUnsupportedCapabilityError(
                f"editing session {self.session_id!r} is closed"
            )

    def _require(self, feature_id: int) -> None:
        if feature_id not in self.layer.rows or feature_id in self.deleted:
            raise QgisSdkLayerNotFoundError(f"{self.layer_id}#{feature_id}")
