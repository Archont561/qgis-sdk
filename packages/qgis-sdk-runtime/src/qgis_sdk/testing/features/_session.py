"""A buffered edit session over one :class:`FakeLayer`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qgis_sdk.models import (
    EditOutcome,
    Geometry,
    QgisSdkFeatureEditError,
    QgisSdkLayerNotFoundError,
    QgisSdkUnsupportedCapabilityError,
)

from ._layer import FakeLayer

__all__ = ["FakeEditingSession"]


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
