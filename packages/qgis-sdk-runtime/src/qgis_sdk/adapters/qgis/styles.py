"""PyQGIS-backed layer appearance: packaged styles, symbology, labelling, style text.

Compatibility is decided before anything is applied, by the same
``StyleSpec.incompatibilities`` rule the fake uses, so a mismatch is refused
without touching the layer. Only symbology is set: the application stylesheet and
palette are never read or written here (decision-16).

The symbology half (TASK-93) describes and builds the four renderers decision-16
allowed and nothing else. Every mapping between a model and a PyQGIS class lives
in one of the tables at the bottom of this module, so a kind that is added to the
model has exactly one place to be taught to this adapter - and a renderer this
adapter was not taught is refused by name instead of being described as the
nearest thing it resembles.

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
    QColor,
    QgsCategorizedSymbolRenderer,
    QgsClassificationCustom,
    QgsClassificationEqualInterval,
    QgsClassificationJenks,
    QgsClassificationPrettyBreaks,
    QgsClassificationQuantile,
    QgsClassificationStandardDeviation,
    QgsFeatureRenderer,
    QgsFillSymbol,
    QgsGraduatedSymbolRenderer,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsRendererCategory,
    QgsRendererRange,
    QgsRuleBasedRenderer,
    QgsSingleSymbolRenderer,
    QgsStyle,
    QgsSymbol,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

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
    CategorizedRenderer,
    Category,
    FillSymbol,
    GraduatedClass,
    GraduatedRenderer,
    Labelling,
    LineSymbol,
    MarkerSymbol,
    Renderer,
    Rule,
    RuleBasedRenderer,
    SingleSymbolRenderer,
    StyleEntry,
    StyleText,
    Symbol,
    symbol_fits_geometry,
)
from qgis_sdk.resources import require_style, style_path

from .layers import NativeLayers

__all__ = ["NativeStyles"]

#: Our graduated mode name -> the classification method a renderer is given.
#: QGIS's method classes are what its own tests construct, and their ids are what
#: comes back when a renderer is read - so this table is read in both directions.
_CLASSIFICATION_METHODS = {
    "equal_interval": QgsClassificationEqualInterval,
    "quantile": QgsClassificationQuantile,
    "jenks": QgsClassificationJenks,
    "std_dev": QgsClassificationStandardDeviation,
    "pretty": QgsClassificationPrettyBreaks,
    # Ranges a user banded themselves: QGIS's own answer for an edited renderer.
    "custom": QgsClassificationCustom,
}

#: The id each method class reports, mapped back to our name. Kept beside the
#: classes above so a reader sees both directions at once.
_METHOD_IDS = {
    "EqualInterval": "equal_interval",
    "Quantile": "quantile",
    "Jenks": "jenks",
    "StdDev": "std_dev",
    "Pretty": "pretty",
    "Custom": "custom",
}


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
        return _describe_renderer(self._vector(layer_id).renderer())

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
        layer.setRenderer(_build_renderer(renderer))
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


# -- describing -----------------------------------------------------------------


def _describe_renderer(renderer: QgsFeatureRenderer) -> Renderer:
    """Translate a PyQGIS renderer into the curated description."""
    if isinstance(renderer, QgsSingleSymbolRenderer):
        return SingleSymbolRenderer(symbol=_describe_symbol(renderer.symbol()))
    if isinstance(renderer, QgsCategorizedSymbolRenderer):
        return CategorizedRenderer(
            field=renderer.classAttribute(),
            categories=tuple(
                Category(
                    value=str(category.value()),
                    label=category.label(),
                    symbol=_describe_symbol(category.symbol()),
                )
                for category in renderer.categories()
            ),
        )
    if isinstance(renderer, QgsGraduatedSymbolRenderer):
        return GraduatedRenderer(
            field=renderer.classAttribute(),
            mode=_classification_mode(renderer),
            classes=tuple(
                GraduatedClass(
                    lower=band.lowerValue(),
                    upper=band.upperValue(),
                    label=band.label(),
                    symbol=_describe_symbol(band.symbol()),
                )
                for band in renderer.ranges()
            ),
        )
    if isinstance(renderer, QgsRuleBasedRenderer):
        return RuleBasedRenderer(
            rules=tuple(_describe_rule(rule) for rule in renderer.rootRule().children())
        )
    raise QgisSdkUnsupportedCapabilityError(
        "symbology", f"{type(renderer).__name__} is not a renderer this SDK describes"
    )


def _classification_mode(renderer: QgsGraduatedSymbolRenderer) -> str:
    """Return our name for the classification method the renderer classifies by."""
    method = renderer.classificationMethod()
    identifier = "" if method is None else method.id()
    mode = _METHOD_IDS.get(identifier)
    if mode is None:
        raise QgisSdkUnsupportedCapabilityError(
            "symbology",
            f"{identifier!r} is not a classification method this SDK names",
        )
    return mode


def _describe_rule(rule: QgsRuleBasedRenderer.Rule) -> Rule:
    """Translate one rule, refusing one this SDK cannot express."""
    if rule.children():
        raise QgisSdkUnsupportedCapabilityError(
            "symbology", "a nested rule group is not a rule this SDK describes"
        )
    if rule.isElse():
        # An else rule draws whatever the other rules did not, which is not an
        # expression a description can carry: mapping it to ``TRUE`` would turn a
        # complement into a catch-all and repaint the layer.
        raise QgisSdkUnsupportedCapabilityError(
            "symbology",
            "an else rule draws the features no other rule matched; this SDK "
            "describes filters, and an else rule has no filter",
        )
    symbol = rule.symbol()
    if symbol is None:
        raise QgisSdkUnsupportedCapabilityError(
            "symbology", "a rule with no symbol has no description in this SDK"
        )
    return Rule(
        filter=rule.filterExpression() or "TRUE",
        label=rule.label(),
        symbol=_describe_symbol(symbol),
        enabled=rule.active(),
    )


def _describe_symbol(symbol: QgsSymbol) -> Symbol:
    """Translate one symbol into a marker, a line or a fill.

    The stroke colour and width come from the first symbol layer, because that is
    where QGIS keeps an outline; a symbol built from several layers is described
    as its first one, which is the curated simplification decision-16 asks for.
    """
    if isinstance(symbol, QgsMarkerSymbol):
        layer = symbol.symbolLayer(0)
        properties = layer.properties()
        return MarkerSymbol(
            color=symbol.color().name(),
            size=symbol.size(),
            shape=str(properties.get("name", "circle")),
            outline_color=layer.strokeColor().name(),
            outline_width=_stroke_width(properties),
        )
    if isinstance(symbol, QgsLineSymbol):
        return LineSymbol(color=symbol.color().name(), width=symbol.width())
    if isinstance(symbol, QgsFillSymbol):
        layer = symbol.symbolLayer(0)
        return FillSymbol(
            color=symbol.color().name(),
            outline_color=layer.strokeColor().name(),
            outline_width=_stroke_width(layer.properties()),
        )
    raise QgisSdkUnsupportedCapabilityError(
        "symbology", f"{type(symbol).__name__} is not a symbol this SDK describes"
    )


def _stroke_width(properties: dict) -> float:
    """Return a symbol layer's outline width; zero means the symbol has none."""
    return float(properties.get("outline_width", 0.0))


# -- building -------------------------------------------------------------------


def _build_renderer(renderer: Renderer) -> QgsFeatureRenderer:
    """Build the PyQGIS renderer a description asks for."""
    if isinstance(renderer, SingleSymbolRenderer):
        return QgsSingleSymbolRenderer(_build_symbol(renderer.symbol))
    if isinstance(renderer, CategorizedRenderer):
        return QgsCategorizedSymbolRenderer(
            renderer.field,
            [
                QgsRendererCategory(
                    category.value, _build_symbol(category.symbol), category.label
                )
                for category in renderer.categories
            ],
        )
    if isinstance(renderer, GraduatedRenderer):
        built = QgsGraduatedSymbolRenderer(
            renderer.field,
            [
                QgsRendererRange(
                    band.lower, band.upper, _build_symbol(band.symbol), band.label
                )
                for band in renderer.classes
            ],
        )
        built.setClassificationMethod(_CLASSIFICATION_METHODS[renderer.mode]())
        return built
    root = QgsRuleBasedRenderer.Rule(None)
    for rule in renderer.rules:
        child = QgsRuleBasedRenderer.Rule(
            _build_symbol(rule.symbol), 0, 0, rule.filter, rule.label
        )
        child.setActive(rule.enabled)
        root.appendChild(child)
    return QgsRuleBasedRenderer(root)


def _build_symbol(symbol: Symbol) -> QgsSymbol:
    """Build the PyQGIS symbol a description asks for."""
    if isinstance(symbol, MarkerSymbol):
        built = QgsMarkerSymbol.createSimple(
            {
                "name": symbol.shape,
                "color": symbol.color,
                "size": str(symbol.size),
                "outline_color": symbol.outline_color,
                "outline_width": str(symbol.outline_width),
            }
        )
        return built
    if isinstance(symbol, LineSymbol):
        return QgsLineSymbol.createSimple(
            {"color": symbol.color, "width": str(symbol.width)}
        )
    return QgsFillSymbol.createSimple(
        {
            "color": symbol.color,
            "outline_color": symbol.outline_color,
            "outline_width": str(symbol.outline_width),
        }
    )
