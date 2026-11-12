from __future__ import annotations

from qgis.core import (
    QgsFeatureRenderer,
    QgsFillSymbol,
    QgsGraduatedSymbolRenderer,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsRuleBasedRenderer,
    QgsSymbol,
)

from qgis_sdk.models import (
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.models.symbology import (
    FillSymbol,
    LineSymbol,
    MarkerSymbol,
    Renderer,
    Rule,
    Symbol,
)

from ._renderer_state import (
    METHOD_IDS,
    CcReturn,
    CcReturn1,
    CcState,
    CcState1,
    cc_build_renderer_p1,
    cc_build_renderer_p2,
    cc_build_renderer_p3,
    cc_describe_rendere_p1,
    cc_describe_rendere_p2,
    cc_describe_rendere_p3,
    cc_describe_rendere_p4,
)


def describe_renderer(renderer: QgsFeatureRenderer) -> Renderer:
    """Translate a PyQGIS renderer into the curated description."""
    _s = CcState(renderer=renderer)
    for _p in (
        cc_describe_rendere_p1,
        cc_describe_rendere_p2,
        cc_describe_rendere_p3,
        cc_describe_rendere_p4,
    ):
        _r = _p(_s)
        if isinstance(_r, CcReturn):
            return _r.value
    return None


def classification_mode(renderer: QgsGraduatedSymbolRenderer) -> str:
    """Return our name for the classification method the renderer classifies by."""
    method = renderer.classificationMethod()
    identifier = "" if method is None else method.id()
    mode = METHOD_IDS.get(identifier)
    if mode is None:
        raise QgisSdkUnsupportedCapabilityError(
            "symbology",
            f"{identifier!r} is not a classification method this SDK names",
        )
    return mode


def describe_rule(rule: QgsRuleBasedRenderer.Rule) -> Rule:
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
        symbol=describe_symbol(symbol),
        enabled=rule.active(),
    )


def describe_symbol(symbol: QgsSymbol) -> Symbol:
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


def build_renderer(renderer: Renderer) -> QgsFeatureRenderer:
    """Build the PyQGIS renderer a description asks for."""
    _s1 = CcState1(renderer=renderer)
    for _p1 in (cc_build_renderer_p1, cc_build_renderer_p2, cc_build_renderer_p3):
        _r1 = _p1(_s1)
        if isinstance(_r1, CcReturn1):
            return _r1.value
    return None


def build_symbol(symbol: Symbol) -> QgsSymbol:
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
