"""Symbology for the native styles adapter: the four renderers decision-16 allowed.

Every mapping between a model and a PyQGIS class lives in one of the tables at
the bottom of this module, so a kind that is added to the model has exactly one
place to be taught to this adapter - and a renderer this adapter was not taught
is refused by name instead of being described as the nearest thing it resembles.

``describe_renderer`` and ``build_renderer`` are the two entry points, and each
drives a phase chain over a mutable record: the phases are here rather than in
``_renderer_state`` because they are the only reason that module would need to
import this one, which would make the two import each other.
"""

from __future__ import annotations

from qgis.core import (
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
    QgsRendererCategory,
    QgsRendererRange,
    QgsRuleBasedRenderer,
    QgsSingleSymbolRenderer,
    QgsSymbol,
)

from qgis_sdk.models import (
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.models.symbology import (
    CategorizedRenderer,
    Category,
    FillSymbol,
    GraduatedClass,
    GraduatedRenderer,
    LineSymbol,
    MarkerSymbol,
    Renderer,
    Rule,
    RuleBasedRenderer,
    SingleSymbolRenderer,
    Symbol,
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


class CcState1:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn1:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def cc_build_renderer_p1(_s1):
    if isinstance(_s1.renderer, SingleSymbolRenderer):
        return CcReturn1(QgsSingleSymbolRenderer(build_symbol(_s1.renderer.symbol)))
    if isinstance(_s1.renderer, CategorizedRenderer):
        return CcReturn1(
            QgsCategorizedSymbolRenderer(
                _s1.renderer.field,
                [
                    QgsRendererCategory(
                        category.value, build_symbol(category.symbol), category.label
                    )
                    for category in _s1.renderer.categories
                ],
            )
        )


def cc_build_renderer_p2(_s1):
    if isinstance(_s1.renderer, GraduatedRenderer):
        _s1.built = QgsGraduatedSymbolRenderer(
            _s1.renderer.field,
            [
                QgsRendererRange(
                    band.lower, band.upper, build_symbol(band.symbol), band.label
                )
                for band in _s1.renderer.classes
            ],
        )
        _s1.built.setClassificationMethod(_CLASSIFICATION_METHODS[_s1.renderer.mode]())
        return CcReturn1(_s1.built)


def cc_build_renderer_p3(_s1):
    _s1.root = QgsRuleBasedRenderer.Rule(None)
    for rule in _s1.renderer.rules:
        _s1.rule = rule
        _s1.child = QgsRuleBasedRenderer.Rule(
            build_symbol(_s1.rule.symbol), 0, 0, _s1.rule.filter, _s1.rule.label
        )
        _s1.child.setActive(_s1.rule.enabled)
        _s1.root.appendChild(_s1.child)
    return CcReturn1(QgsRuleBasedRenderer(_s1.root))


class CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def cc_describe_rendere_p1(_s):
    if isinstance(_s.renderer, QgsSingleSymbolRenderer):
        return CcReturn(
            SingleSymbolRenderer(symbol=describe_symbol(_s.renderer.symbol()))
        )


def cc_describe_rendere_p2(_s):
    if isinstance(_s.renderer, QgsCategorizedSymbolRenderer):
        return CcReturn(
            CategorizedRenderer(
                field=_s.renderer.classAttribute(),
                categories=tuple(
                    Category(
                        value=str(category.value()),
                        label=category.label(),
                        symbol=describe_symbol(category.symbol()),
                    )
                    for category in _s.renderer.categories()
                ),
            )
        )


def cc_describe_rendere_p3(_s):
    if isinstance(_s.renderer, QgsGraduatedSymbolRenderer):
        return CcReturn(
            GraduatedRenderer(
                field=_s.renderer.classAttribute(),
                mode=classification_mode(_s.renderer),
                classes=tuple(
                    GraduatedClass(
                        lower=band.lowerValue(),
                        upper=band.upperValue(),
                        label=band.label(),
                        symbol=describe_symbol(band.symbol()),
                    )
                    for band in _s.renderer.ranges()
                ),
            )
        )


def cc_describe_rendere_p4(_s):
    if isinstance(_s.renderer, QgsRuleBasedRenderer):
        return CcReturn(
            RuleBasedRenderer(
                rules=tuple(
                    describe_rule(rule) for rule in _s.renderer.rootRule().children()
                )
            )
        )
    raise QgisSdkUnsupportedCapabilityError(
        "symbology",
        f"{type(_s.renderer).__name__} is not a renderer this SDK describes",
    )


_CLASSIFICATION_METHODS = {
    "equal_interval": QgsClassificationEqualInterval,
    "quantile": QgsClassificationQuantile,
    "jenks": QgsClassificationJenks,
    "std_dev": QgsClassificationStandardDeviation,
    "pretty": QgsClassificationPrettyBreaks,
    # Ranges a user banded themselves: QGIS's own answer for an edited renderer.
    "custom": QgsClassificationCustom,
}
METHOD_IDS = {
    "EqualInterval": "equal_interval",
    "Quantile": "quantile",
    "Jenks": "jenks",
    "StdDev": "std_dev",
    "Pretty": "pretty",
    "Custom": "custom",
}
