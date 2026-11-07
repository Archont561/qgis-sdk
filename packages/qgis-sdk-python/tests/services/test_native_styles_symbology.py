"""Native-only: the edges of symbology that only real QGIS can show.

The contract suite already holds both backends to the same round trips. What is
left here are the claims that cannot be faked:

* a renderer this SDK does not model is refused *by name* rather than described
  as the nearest thing it resembles - the refusal is read off a real
  ``QgsHeatmapRenderer``, which is what a user may well have on their layer;
* a fill symbol round-trips on a polygon layer, which the contract cannot cover
  because the reference fixtures hold points and lines only;
* QML reproduces **every** renderer, which is TASK-93's acceptance criterion
  stated in full - the contract proves the categorized case on both backends,
  and this proves the other three against the dialect a user actually saves;
* the real default style is what ``list_styles`` answers;
* the two labelling states that are not a simple labelling: labels switched on
  with no labelling object, and a labelling rule set.

It needs a real QGIS host, so it is skipped unless ``QGIS_SDK_NATIVE_SERVICES=1``
- and it asks for ``native_services`` rather than ``services``, because a claim
about real QGIS must not be answered by a fake.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from qgis_sdk.models import (
    CategorizedRenderer,
    Category,
    FillSymbol,
    GraduatedClass,
    GraduatedRenderer,
    LineSymbol,
    MarkerSymbol,
    QgisSdkUnsupportedCapabilityError,
    Rule,
    RuleBasedRenderer,
    SingleSymbolRenderer,
)

pytestmark = pytest.mark.qgis

if TYPE_CHECKING:
    from pathlib import Path

    from .conftest import Services

RED = "#ff0000"
BLUE = "#0000ff"
GREEN = "#00ff00"

#: The three reference points as a GeoJSON polygon, written where the native
#: backend can read it: a polygon layer is the one geometry the checked-in
#: fixtures do not carry, and a fill symbol is the one symbol kind they cannot
#: prove.
POLYGON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"value": "a"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[21.0, 52.0], [21.2, 52.0], [21.2, 52.2], [21.0, 52.0]]
                ],
            },
        }
    ],
}

#: One renderer per kind, all legal on a point layer.
RENDERERS = (
    pytest.param(SingleSymbolRenderer(symbol=MarkerSymbol(RED)), id="single"),
    pytest.param(
        CategorizedRenderer(
            field="value",
            categories=(
                Category(value="a", label="A", symbol=MarkerSymbol(RED)),
                Category(value="b", label="B", symbol=MarkerSymbol(BLUE)),
            ),
        ),
        id="categorized",
    ),
    pytest.param(
        GraduatedRenderer(
            field="value",
            mode="jenks",
            classes=(
                GraduatedClass(
                    lower=0.0, upper=1.0, label="0-1", symbol=MarkerSymbol(RED)
                ),
                GraduatedClass(
                    lower=1.0, upper=2.0, label="1-2", symbol=MarkerSymbol(BLUE)
                ),
            ),
        ),
        id="graduated",
    ),
    pytest.param(
        RuleBasedRenderer(
            rules=(
                Rule(filter="value = 1", label="Low", symbol=MarkerSymbol(RED)),
                Rule(
                    filter="value = 2",
                    label="High",
                    symbol=MarkerSymbol(BLUE),
                    enabled=False,
                ),
            )
        ),
        id="rule_based",
    ),
)


def _points(native_services: Services) -> str:
    return native_services.layers.open_vector(native_services.dataset).id


def _colours(renderer) -> tuple[str, ...]:
    if isinstance(renderer, SingleSymbolRenderer):
        return (renderer.symbol.color,)
    if isinstance(renderer, CategorizedRenderer):
        return tuple(category.symbol.color for category in renderer.categories)
    if isinstance(renderer, GraduatedRenderer):
        return tuple(band.symbol.color for band in renderer.classes)
    return tuple(rule.symbol.color for rule in renderer.rules)


def _shape_of(renderer) -> tuple[object, ...]:
    """What a renderer describes, minus the labels QGIS regenerates.

    A graduated renderer's label is a *rendering* of its classification method:
    QGIS can rewrite ``"0-1"`` as its method's own label text when the document is
    loaded, so a round trip is asserted on the bands and the colours - the things
    that decide what the map shows - and not on the caption a user could have
    typed over.
    """
    if isinstance(renderer, GraduatedRenderer):
        return (
            renderer.kind,
            renderer.field,
            renderer.mode,
            tuple(
                (band.lower, band.upper, band.symbol.color) for band in renderer.classes
            ),
        )
    if isinstance(renderer, RuleBasedRenderer):
        return (
            renderer.kind,
            tuple(
                (
                    " ".join(rule.filter.split()),
                    rule.label,
                    rule.symbol.color,
                    rule.enabled,
                )
                for rule in renderer.rules
            ),
        )
    if isinstance(renderer, CategorizedRenderer):
        return (
            renderer.kind,
            renderer.field,
            tuple(
                (category.value, category.label, category.symbol.color)
                for category in renderer.categories
            ),
        )
    return (renderer.kind, renderer.symbol)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_qml_reproduces_every_supported_renderer(
    native_services: Services, renderer: object
) -> None:
    layer_id = _points(native_services)
    native_services.styles.set_symbology(layer_id, renderer)

    text = native_services.styles.export_style(layer_id, "qml")

    # Something else in between, so the import has to be what brought it back.
    native_services.styles.set_symbology(
        layer_id, SingleSymbolRenderer(MarkerSymbol(GREEN))
    )
    assert native_services.styles.symbology(layer_id).kind == "single_symbol"

    native_services.styles.import_style(layer_id, text.text, "qml")

    assert _shape_of(native_services.styles.symbology(layer_id)) == _shape_of(renderer)


def test_a_fill_symbol_round_trips_on_a_polygon_layer(
    native_services: Services, tmp_path: Path
) -> None:
    source = tmp_path / "areas.geojson"
    source.write_text(json.dumps(POLYGON), encoding="utf-8")
    layer_id = native_services.layers.open_vector(source).id
    # A fresh polygon layer starts drawn with a fill, exactly as a point layer
    # starts with a marker - the geometry decides the symbol kind.
    fresh = native_services.styles.symbology(layer_id)
    assert isinstance(fresh, SingleSymbolRenderer), fresh
    assert fresh.symbol.kind == "fill"

    # A zero-width outline is a fill with no border, which is a real choice.
    native_services.styles.set_symbology(
        layer_id, SingleSymbolRenderer(symbol=FillSymbol(BLUE, outline_width=0.0))
    )

    answered = native_services.styles.symbology(layer_id)
    assert answered.symbol.kind == "fill"
    assert answered.symbol.color == BLUE
    assert answered.symbol.outline_width == 0.0


def test_a_line_layer_keeps_its_line_symbol_through_qml(
    native_services: Services,
) -> None:
    layer_id = native_services.layers.open_vector(native_services.line_dataset).id
    renderer = SingleSymbolRenderer(symbol=LineSymbol(color=GREEN, width=1.5))
    native_services.styles.set_symbology(layer_id, renderer)

    text = native_services.styles.export_style(layer_id, "qml")
    native_services.styles.set_symbology(
        layer_id, SingleSymbolRenderer(symbol=LineSymbol(color=RED))
    )
    native_services.styles.import_style(layer_id, text.text, "qml")

    answered = native_services.styles.symbology(layer_id)
    assert answered == renderer


def test_a_renderer_this_sdk_does_not_model_is_refused_by_name(
    native_services: Services,
) -> None:
    """A heatmap is a real renderer a user can have; it is not one we describe."""
    from qgis.core import QgsHeatmapRenderer

    layer_id = _points(native_services)
    native_services.layers._qgs_layer(layer_id).setRenderer(QgsHeatmapRenderer())

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as error:
        native_services.styles.symbology(layer_id)

    assert "QgsHeatmapRenderer" in str(error.value), str(error.value)


def test_a_labelling_rule_set_is_refused_rather_than_flattened(
    native_services: Services,
) -> None:
    """decision-16 allows *simple* labelling; a rule set is more, and is named."""
    from qgis.core import (
        QgsPalLayerSettings,
        QgsRuleBasedLabeling,
        QgsVectorLayerSimpleLabeling,
    )

    layer_id = _points(native_services)
    layer = native_services.layers._qgs_layer(layer_id)
    settings = QgsPalLayerSettings()
    settings.fieldName = "value"
    settings.drawLabels = True
    root = QgsRuleBasedLabeling.Rule(settings)
    layer.setLabeling(QgsRuleBasedLabeling(root))
    layer.setLabelsEnabled(True)

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as error:
        native_services.styles.labelling(layer_id)

    assert "RuleBasedLabeling" in str(error.value) or "rule set" in str(error.value)
    assert QgsVectorLayerSimpleLabeling is not None


def test_labels_switched_on_with_nothing_to_draw_them_answer_off(
    native_services: Services,
) -> None:
    """QGIS keeps the flag but no labelling object; that layer has no labelling."""
    layer_id = _points(native_services)
    layer = native_services.layers._qgs_layer(layer_id)
    layer.setLabeling(None)
    layer.setLabelsEnabled(True)

    assert native_services.styles.labelling(layer_id).enabled is False


def test_the_style_manager_answers_the_default_style(native_services: Services) -> None:
    entries = native_services.styles.list_styles()

    assert entries, "a QGIS install always has a default style"
    names = {"symbol": [], "color_ramp": [], "label_settings": []}
    for entry in entries:
        names[entry.kind].append(entry.name)
    # Sorted within a kind, because a page offers a sorted list and a host that
    # reordered it would make two runs answer differently.
    for kind, listed in names.items():
        assert listed == sorted(listed), kind
    assert names["symbol"], "the default style holds symbols"
    assert names["color_ramp"], "the default style holds colour ramps"


def test_every_named_symbol_is_one_the_sdk_could_describe(
    native_services: Services,
) -> None:
    """A listed name is a promise; the promise is that QGIS knows it too."""
    from qgis.core import QgsStyle

    style = QgsStyle.defaultStyle()
    for entry in native_services.styles.list_styles("symbol"):
        assert style.symbol(entry.name) is not None, entry.name
