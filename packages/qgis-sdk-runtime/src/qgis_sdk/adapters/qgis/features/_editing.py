"""One layer's edit buffer, as the view's session."""

from __future__ import annotations

from qgis.core import QgsFeature, QgsFeatureRequest, QgsVectorLayer

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    EditOutcome,
    Geometry,
    QgisSdkLayerNotFoundError,
    QgisSdkUnsupportedCapabilityError,
)

from ._geometry import decode

__all__ = ["NativeFeatureEditing"]


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
            feature.setGeometry(decode(geometry))
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
            feature.setGeometry(decode(geometry))
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
