"""PyQGIS-backed layer appearance: packaged styles, symbology, labelling, style text.

Compatibility is decided before anything is applied, by the same
``StyleSpec.incompatibilities`` rule the fake uses, so a mismatch is refused
without touching the layer. Only symbology is set: the application stylesheet and
palette are never read or written here (decision-16).

Symbology itself - the four renderers decision-16 allowed, and the symbol and
rule descriptions they are built from - lives in ``_renderers``, which this
module drives and which holds every mapping between a model and a PyQGIS
class. This half owns the layer-facing operations: applying a packaged style,
reading and setting the renderer, labelling and style text.

QML and SLD cross as text, and the bridge to and from text is a file:
``saveNamedStyle``/``loadNamedStyle`` and ``saveSldStyle``/``loadSldStyle`` are
the public, non-deprecated, version-stable entry points, while the document-based
forms are either deprecated in 3.44 (``exportSldStyle``) or take a ``QString &``
out-parameter that a Python caller cannot fill in. One temporary directory per
call is the price of using the API QGIS actually keeps.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from qgis.core import (
    QgsPalLayerSettings,
    QgsStyle,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor

from qgis_sdk.adapters.qgis.layers import NativeLayers
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    QgisSdkPackagedResourceError,
    QgisSdkStyleIncompatibleError,
    QgisSdkStyleTextError,
    QgisSdkUnsupportedCapabilityError,
    VectorLayerInfo,
)
from qgis_sdk.models.symbology import (
    STYLE_MANAGER_KINDS,
    Labelling,
    Renderer,
    StyleEntry,
    StyleText,
    symbol_fits_geometry,
)
from qgis_sdk.resources import require_style, style_path

from ._renderers import build_renderer, describe_renderer


class NativeStyles:
    """Apply packaged QML, and read and write a layer's symbology."""

    def __init__(self, layers: NativeLayers, scope: ResourceScope) -> None:
        self._layers = layers
        self._scope = scope

    # -- packaged styles (TASK-25.4) -----------------------------------------

    def apply_style(self, layer_id: str, style: str) -> None:
        """Validate the target, then load the packaged QML onto the layer."""
        self._scope.ensure_open()
        info = self._layers.layer(layer_id)
        spec = require_style(style)
        reasons = spec.incompatibilities(info)
        if reasons:
            raise QgisSdkStyleIncompatibleError(layer_id, style, reasons)

        resource = style_path(style)
        # Package handoff: the style must be loaded onto the very instance the
        # layers adapter owns, not a copy of its description.
        layer = self._layers._qgs_layer(layer_id)
        message, loaded = layer.loadNamedStyle(str(resource))
        if not loaded:
            raise QgisSdkPackagedResourceError(style, message or "QGIS rejected it")

    # -- symbology (TASK-93) -------------------------------------------------

    def symbology(self, layer_id: str) -> Renderer:
        """Describe the renderer drawing ``layer_id``."""
        return describe_renderer(self._vector(layer_id).renderer())

    def set_symbology(self, layer_id: str, renderer: Renderer) -> None:
        """Build the renderer from the description and hand it to the layer.

        A symbol whose kind the layer's geometry cannot draw is refused *before*
        the renderer is built, because QGIS accepts the mismatch and then draws
        nothing: the same rule the fake applies, from the same helper, so the two
        backends cannot disagree about which descriptions are legal.
        """
        layer = self._vector(layer_id)
        info = self._layers.layer(layer_id)
        reason = symbol_fits_geometry(renderer, info.geometry_type)
        if reason is not None:
            raise QgisSdkStyleIncompatibleError(layer_id, renderer.kind, (reason,))
        layer.setRenderer(build_renderer(renderer))
        layer.triggerRepaint()

    def labelling(self, layer_id: str) -> Labelling:
        """Describe how ``layer_id``'s features are labelled."""
        layer = self._vector(layer_id)
        if not layer.labelsEnabled():
            return Labelling()
        labeling = layer.labeling()
        if labeling is None:
            # Labels switched on with nothing to draw them: QGIS keeps the flag
            # and no labelling object, which is the layer saying "nothing yet".
            return Labelling()
        if not isinstance(labeling, QgsVectorLayerSimpleLabeling):
            raise QgisSdkUnsupportedCapabilityError(
                layer_id,
                f"{type(labeling).__name__} is a labelling rule set, "
                "not the simple labelling this SDK describes",
            )
        settings = labeling.settings()
        text_format = settings.format()
        return Labelling(
            enabled=True,
            field=settings.fieldName or None,
            size=text_format.size(),
            color=text_format.color().name(),
        )

    def set_labelling(self, layer_id: str, labelling: Labelling) -> None:
        """Turn simple labelling on with a field, or off."""
        layer = self._vector(layer_id)
        if not labelling.enabled:
            layer.setLabelsEnabled(False)
            layer.triggerRepaint()
            return
        settings = QgsPalLayerSettings()
        settings.fieldName = labelling.field
        # ``drawLabels`` is the member both QGIS 3.44 and 4.x expose; the older
        # ``enabled`` flag is gone in 4.x, and the layer's own
        # ``setLabelsEnabled`` below is what a map actually reads.
        settings.drawLabels = True
        text_format = QgsTextFormat()
        text_format.setSize(labelling.size)
        text_format.setColor(QColor(labelling.color))
        settings.setFormat(text_format)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()

    # -- the style manager and style text ------------------------------------

    def list_styles(self, kind: str | None = None) -> tuple[StyleEntry, ...]:
        """Answer what the default QGIS style holds, sorted by name."""
        self._scope.ensure_open()
        if kind is not None and kind not in STYLE_MANAGER_KINDS:
            raise ValueError(
                f"a style manager kind is one of {', '.join(STYLE_MANAGER_KINDS)}, "
                f"not {kind!r}"
            )
        style = QgsStyle.defaultStyle()
        readers = {
            "symbol": style.symbolNames,
            "color_ramp": style.colorRampNames,
            "label_settings": style.labelSettingsNames,
        }
        entries: list[StyleEntry] = []
        for name_kind in STYLE_MANAGER_KINDS:
            if kind is not None and name_kind != kind:
                continue
            entries.extend(
                StyleEntry(name=str(name), kind=name_kind)
                for name in sorted(readers[name_kind]())
            )
        return tuple(entries)

    def export_style(self, layer_id: str, format: str) -> StyleText:
        """Write the layer's style to a file and answer the file's text."""
        layer = self._vector(layer_id)
        with tempfile.TemporaryDirectory(prefix="qgis-sdk-style-") as directory:
            path = Path(directory) / f"style.{format}"
            message, written = _save_style(layer, path, format)
            if not written or not path.is_file():
                raise QgisSdkPackagedResourceError(
                    f"layer {layer_id}", message or f"QGIS wrote no {format} text"
                )
            return StyleText(format=format, text=path.read_text(encoding="utf-8"))

    def import_style(self, layer_id: str, text: str, format: str) -> None:
        """Write the text to a file and ask QGIS to load it onto the layer."""
        layer = self._vector(layer_id)
        with tempfile.TemporaryDirectory(prefix="qgis-sdk-style-") as directory:
            path = Path(directory) / f"style.{format}"
            path.write_text(text, encoding="utf-8")
            message, loaded = _load_style(layer, path, format)
        if not loaded:
            raise QgisSdkStyleTextError(format, message or "QGIS rejected the document")
        layer.triggerRepaint()

    def _vector(self, layer_id: str) -> QgsVectorLayer:
        """Return the native vector layer, refusing every other kind by name."""
        self._scope.ensure_open()
        info = self._layers.layer(layer_id)
        if not isinstance(info, VectorLayerInfo):
            raise QgisSdkUnsupportedCapabilityError(
                info.id,
                f"a {info.kind} is drawn by QGIS, not by a renderer this SDK sets",
            )
        return self._layers._qgs_layer(layer_id)


def _save_style(layer: QgsVectorLayer, path: Path, format: str) -> tuple[str, bool]:
    """Write the layer's style to ``path`` in ``format``, answering QGIS's message."""
    if format == "qml":
        return layer.saveNamedStyle(str(path))
    return layer.saveSldStyle(str(path))


def _load_style(layer: QgsVectorLayer, path: Path, format: str) -> tuple[str, bool]:
    """Read a style document from ``path`` onto the layer."""
    if format == "qml":
        return layer.loadNamedStyle(str(path))
    return layer.loadSldStyle(str(path))
