"""Pickers: LayerPicker, FieldPicker and CrsPicker over the ui context."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from qgis_sdk.models import (
    LAYER_KIND_NAMES,
    LAYER_KINDS_FOR_INPUT,
    QgisSdkFormError,
    QgisSdkLayerNotFoundError,
    QgisSdkUiError,
)
from qgis_sdk.ui.components._base import Input, Option

# -- pickers --------------------------------------------------------------------------


class _Picker(Input):
    """A component that chooses among listed options; the value is an id or ``None``."""

    def options(self) -> tuple[Option, ...]:
        """What the picker currently lists, in display order."""
        if self._native is not None:
            listed = self._native.options()
            if listed is not None:
                return listed
        return self._list()

    def _list(self) -> tuple[Option, ...]:
        return ()

    def _refreshed(self) -> None:
        if self._value is not None and self._value not in {
            option.id for option in self.options()
        }:
            self._commit(None)

    def _snapshot_options(self) -> list[dict[str, str]]:
        return [{"id": option.id, "label": option.label} for option in self.options()]


#: The kinds a picker accepts: every ``LayerInput`` kind, plus ``"any"``. Spelled
#: as a type for editors; the gate is :data:`LAYER_KINDS_FOR_INPUT` at runtime.
LayerKindInput = Literal[
    "vector",
    "raster",
    "mesh",
    "point_cloud",
    "vector_tile",
    "annotation",
    "tiled_scene",
    "any",
]


class LayerPicker(_Picker):
    """A layer of the open project; the value is its layer id or ``None``.

    ``kind`` filters what is listed: ``"vector"`` (the default), any other layer
    kind, or ``"any"``, which lists all of them. The list of accepted kinds is the
    one a ``LayerInput`` accepts, so a picker cannot refuse a kind the input
    lets a declaration name. Natively this is ``QgsMapLayerComboBox``, which follows the
    project on its own; under the fake the list comes from ``ctx.layers`` -
    the all-kinds service TASK-87 lands - and :meth:`refresh` re-reads it. The
    project is consulted first so the picker matches the tree's order, and a
    layer the project holds but the layer service no longer knows is skipped
    rather than listed as a dead id.
    """

    kind = "layer"

    def __init__(
        self,
        name: str | None = None,
        *,
        kind: LayerKindInput = "vector",
        label: str | None = None,
        value: object = None,
        required: bool = False,
    ) -> None:
        if kind not in LAYER_KINDS_FOR_INPUT:
            raise QgisSdkUiError(
                f"LayerPicker {name!r}: kind must be one of "
                f"{', '.join(LAYER_KINDS_FOR_INPUT)}, got {kind!r}"
            )
        self.layer_kind = kind
        super().__init__(name, label=label, value=value, required=required)

    def _list(self) -> tuple[Option, ...]:
        ctx = self._ctx
        if ctx is None or not ctx.has("layers"):
            return ()
        wanted = LAYER_KIND_NAMES if self.layer_kind == "any" else (self.layer_kind,)
        known = {
            info.id: info for info in ctx.layers.list_layers() if info.kind in wanted
        }
        ids: Iterable[str]
        if ctx.has("project"):
            ids = ctx.project.layer_ids()
        else:
            ids = known
        listed: list[Option] = []
        seen: set[str] = set()
        for layer_id in ids:
            if layer_id in seen:
                continue
            seen.add(layer_id)
            info = known.get(layer_id)
            if info is None:
                try:
                    info = ctx.layers.layer(layer_id)
                except QgisSdkLayerNotFoundError:
                    continue
                if info.kind not in wanted:
                    continue
            listed.append(Option(id=info.id, label=info.name))
        return tuple(listed)

    def _accept(self, value: object) -> object:
        if value is None:
            return None
        if value not in {option.id for option in self.options()}:
            raise QgisSdkFormError(
                f"{self._describe()}: layer {value!r} is not in the project"
            )
        return value

    def _details(self) -> dict[str, Any]:
        return {"layers": self.layer_kind}

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["options"] = self._snapshot_options()
        return node


class FieldPicker(_Picker):
    """A field of the layer another picker chose; the value is the field name or ``None``.

    ``of`` is the :class:`LayerPicker` to follow: when its layer changes the
    field list is re-read and a field the new layer lacks is dropped.
    """

    kind = "field"

    def __init__(
        self,
        name: str | None = None,
        *,
        of: LayerPicker,
        label: str | None = None,
        value: object = None,
        required: bool = False,
    ) -> None:
        if not isinstance(of, LayerPicker):
            raise QgisSdkUiError(f"FieldPicker {name!r}: of= must be a LayerPicker")
        self.of = of
        self._unfollow = of.changed(lambda _layer: self.refresh())
        super().__init__(name, label=label, value=value, required=required)

    def _list(self) -> tuple[Option, ...]:
        ctx = self._ctx
        layer_id = self.of.value()
        if ctx is None or layer_id is None or not ctx.has("layers"):
            return ()
        try:
            info = ctx.layers.layer(layer_id)
        except QgisSdkLayerNotFoundError:
            return ()
        return tuple(Option(id=name, label=name) for name in info.field_names)

    def _refreshed(self) -> None:
        if self._native is not None:
            self._syncing = True
            try:
                self._native.apply(self._value)
            finally:
                self._syncing = False
        super()._refreshed()

    def _accept(self, value: object) -> object:
        if value is None:
            return None
        if value not in {option.id for option in self.options()}:
            raise QgisSdkFormError(
                f"{self._describe()}: {value!r} is not a field of the chosen layer"
            )
        return value

    def _detached(self) -> None:
        self._unfollow()

    def _details(self) -> dict[str, Any]:
        return {"of": self.of.name}

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["options"] = self._snapshot_options()
        return node


class CrsPicker(Input):
    """A coordinate reference system; the value is its authority id (``EPSG:4326``) or ``None``."""

    kind = "crs"

    def _accept(self, value: object) -> object:
        if value is None:
            return None
        authority, separator, code = str(value).partition(":")
        if not separator or not authority.strip() or not code.strip():
            raise QgisSdkFormError(
                f"{self._describe()}: field {self.name} expects an authority id "
                f"such as 'EPSG:4326', got {value!r}"
            )
        return f"{authority.strip().upper()}:{code.strip()}"
