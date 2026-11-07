"""Contract: symbology, labelling and style text, on every backend (TASK-93).

decision-16 allowed four renderers, three symbols and one simple labelling; these
tests are what "allowed" means in practice, because both backends answer them:

* a description that went through ``set_symbology`` comes back out of
  ``symbology`` unchanged, for every supported renderer - the fake answers from
  the description it stored, so a failure here is the native adapter disagreeing
  with the model;
* a symbol whose kind the layer's geometry cannot draw is refused with the same
  error on both backends, through the same model helper;
* QML reproduces the renderer, and SLD reproduces *the drawing*.

That last difference is not laziness. SLD has no notion of "categorized": QGIS
writes a categorized renderer out as one rule per category and reads it back as a
rule-based renderer, so the renderer a page gets after an SLD round trip is not
the renderer it wrote. What survives is what the map looks like - the colours, in
the same order - and that is what this file asserts. QML is QGIS's own format and
does carry the renderer kind, so it is held to the stricter claim.

The native-only edges (an unmodelled renderer refused by name, the real default
style listing, a fill symbol on a polygon layer) live in
``test_native_styles_symbology.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qgis_sdk.models import (
    CategorizedRenderer,
    Category,
    GraduatedClass,
    GraduatedRenderer,
    Labelling,
    LineSymbol,
    MarkerSymbol,
    QgisSdkStyleIncompatibleError,
    QgisSdkUnsupportedCapabilityError,
    Rule,
    RuleBasedRenderer,
    SingleSymbolRenderer,
    StyleEntry,
)
from qgis_sdk.models.symbology import GRADUATED_MODES, STYLE_MANAGER_KINDS, symbol_kind

if TYPE_CHECKING:
    from .conftest import Services

#: Colours that survive a text round trip through either dialect, spelled the way
#: the model stores them so a comparison needs no normalising.
RED = "#ff0000"
BLUE = "#0000ff"
GREEN = "#00ff00"

#: One renderer per kind, all legal on the point fixture: a marker description on
#: a layer of points is what a page actually sets.
RENDERERS = (
    pytest.param(
        "single_symbol", SingleSymbolRenderer(symbol=MarkerSymbol(RED)), id="single"
    ),
    pytest.param(
        "categorized",
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
        "graduated",
        GraduatedRenderer(
            field="value",
            mode="quantile",
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
        "rule_based",
        RuleBasedRenderer(
            rules=(
                Rule(filter="value = 1", label="Low", symbol=MarkerSymbol(RED)),
                Rule(filter="value = 2", label="High", symbol=MarkerSymbol(BLUE)),
            )
        ),
        id="rule_based",
    ),
)


def _points(services: Services) -> str:
    """The reference point layer, opened the way a user opens it."""
    return services.layers.open_vector(services.dataset).id


def _lines(services: Services) -> str:
    return services.layers.open_vector(services.line_dataset).id


def _filters(renderer: RuleBasedRenderer) -> list[str]:
    """The rules' filters, with whitespace collapsed.

    QGIS stores a filter as a parsed expression and writes it back out of the
    parse tree, so ``"value = 1"`` may come back with different spacing. The
    filter's *meaning* is what the round trip is about, not its layout.
    """
    return [" ".join(rule.filter.split()) for rule in renderer.rules]


def _colours(renderer) -> tuple[str, ...]:
    """Every colour a renderer paints with, in declaration order."""
    if isinstance(renderer, SingleSymbolRenderer):
        return (renderer.symbol.color,)
    if isinstance(renderer, CategorizedRenderer):
        return tuple(category.symbol.color for category in renderer.categories)
    if isinstance(renderer, GraduatedRenderer):
        return tuple(band.symbol.color for band in renderer.classes)
    return tuple(rule.symbol.color for rule in renderer.rules)


def test_a_fresh_layer_answers_a_single_symbol_renderer(services: Services) -> None:
    renderer = services.styles.symbology(_points(services))

    assert isinstance(renderer, SingleSymbolRenderer), renderer
    assert renderer.symbol.kind == "marker", renderer.symbol


def test_a_line_layer_starts_with_a_line_symbol(services: Services) -> None:
    renderer = services.styles.symbology(_lines(services))

    assert isinstance(renderer, SingleSymbolRenderer), renderer
    assert renderer.symbol.kind == "line", renderer.symbol


@pytest.mark.parametrize(("kind", "renderer"), RENDERERS)
def test_every_supported_renderer_round_trips(
    services: Services, kind: str, renderer: object
) -> None:
    layer_id = _points(services)

    services.styles.set_symbology(layer_id, renderer)

    assert services.styles.symbology(layer_id) == renderer, kind


@pytest.mark.parametrize("mode", GRADUATED_MODES)
def test_every_graduated_mode_survives_the_round_trip(
    services: Services, mode: str
) -> None:
    layer_id = _points(services)
    renderer = GraduatedRenderer(
        field="value",
        mode=mode,
        classes=(
            GraduatedClass(lower=0.0, upper=1.0, label="0-1", symbol=MarkerSymbol(RED)),
            GraduatedClass(
                lower=1.0, upper=2.0, label="1-2", symbol=MarkerSymbol(BLUE)
            ),
        ),
    )

    services.styles.set_symbology(layer_id, renderer)

    answered = services.styles.symbology(layer_id)
    assert isinstance(answered, GraduatedRenderer), answered
    assert answered.mode == mode


def test_a_rule_based_renderer_keeps_its_filters_and_its_switch(
    services: Services,
) -> None:
    layer_id = _points(services)
    renderer = RuleBasedRenderer(
        rules=(
            Rule(filter="value = 1", label="Low", symbol=MarkerSymbol(RED)),
            Rule(
                filter="value = 2",
                label="High",
                symbol=MarkerSymbol(BLUE),
                enabled=False,
            ),
        )
    )

    services.styles.set_symbology(layer_id, renderer)

    answered = services.styles.symbology(layer_id)
    assert isinstance(answered, RuleBasedRenderer), answered
    assert _filters(answered) == ["value = 1", "value = 2"]
    assert [rule.enabled for rule in answered.rules] == [True, False]


def test_a_marker_keeps_its_colour_size_and_outline(services: Services) -> None:
    layer_id = _points(services)
    symbol = MarkerSymbol(
        color=RED, size=3.5, shape="star", outline_color=BLUE, outline_width=0.25
    )

    services.styles.set_symbology(layer_id, SingleSymbolRenderer(symbol=symbol))

    answered = services.styles.symbology(layer_id)
    assert answered.symbol == symbol


def test_a_marker_with_no_outline_round_trips(services: Services) -> None:
    """A zero-width outline is a real choice - a marker with no border - not a bug."""
    layer_id = _points(services)
    symbol = MarkerSymbol(color=RED, size=2.0, outline_width=0.0)

    services.styles.set_symbology(layer_id, SingleSymbolRenderer(symbol=symbol))

    answered = services.styles.symbology(layer_id)
    assert answered.symbol.outline_width == 0.0


def test_a_line_symbol_round_trips(services: Services) -> None:
    layer_id = _lines(services)
    symbol = LineSymbol(color=GREEN, width=1.5)

    services.styles.set_symbology(layer_id, SingleSymbolRenderer(symbol=symbol))

    answered = services.styles.symbology(layer_id)
    assert answered.symbol == symbol


def test_a_marker_on_a_line_layer_is_refused(services: Services) -> None:
    """QGIS would accept this and draw nothing: the SDK refuses it instead."""
    layer_id = _lines(services)

    with pytest.raises(QgisSdkStyleIncompatibleError) as error:
        services.styles.set_symbology(
            layer_id, SingleSymbolRenderer(symbol=MarkerSymbol(RED))
        )

    assert error.value.layer_id == layer_id
    assert "marker" in str(error.value)
    assert "line" in str(error.value)


def test_labelling_round_trips(services: Services) -> None:
    layer_id = _points(services)
    labelling = Labelling(enabled=True, field="value", size=9, color=BLUE)

    services.styles.set_labelling(layer_id, labelling)
    assert services.styles.labelling(layer_id) == labelling

    services.styles.set_labelling(layer_id, Labelling())
    assert services.styles.labelling(layer_id).enabled is False


def test_a_fresh_layer_is_not_labelled(services: Services) -> None:
    assert services.styles.labelling(_points(services)).enabled is False


def test_qml_export_import_reproduces_the_renderer(services: Services) -> None:
    layer_id = _points(services)
    renderer = CategorizedRenderer(
        field="value",
        categories=(
            Category(value="a", label="A", symbol=MarkerSymbol(RED, size=3.5)),
            Category(value="b", label="B", symbol=MarkerSymbol(BLUE, size=3.5)),
        ),
    )
    services.styles.set_symbology(layer_id, renderer)

    text = services.styles.export_style(layer_id, "qml")
    services.styles.set_symbology(
        layer_id, SingleSymbolRenderer(symbol=MarkerSymbol(GREEN))
    )
    services.styles.import_style(layer_id, text.text, "qml")

    assert services.styles.symbology(layer_id) == renderer


def test_sld_export_import_reproduces_the_drawing(services: Services) -> None:
    layer_id = _points(services)
    renderer = CategorizedRenderer(
        field="value",
        categories=(
            Category(value="a", label="A", symbol=MarkerSymbol(RED, size=3.5)),
            Category(value="b", label="B", symbol=MarkerSymbol(BLUE, size=3.5)),
        ),
    )
    services.styles.set_symbology(layer_id, renderer)

    text = services.styles.export_style(layer_id, "sld")
    services.styles.set_symbology(
        layer_id, SingleSymbolRenderer(symbol=MarkerSymbol(GREEN))
    )
    services.styles.import_style(layer_id, text.text, "sld")

    # The kind is not part of the claim: SLD carries rules, not our vocabulary.
    answered = services.styles.symbology(layer_id)
    assert _colours(answered) == (RED, BLUE), answered
    assert symbol_kind(answered) == "marker"


def test_style_text_of_the_wrong_dialect_is_refused(services: Services) -> None:
    layer_id = _points(services)
    qml = services.styles.export_style(layer_id, "qml")

    with pytest.raises(Exception) as error:
        services.styles.import_style(layer_id, qml.text, "sld")

    assert not isinstance(error.value, QgisSdkUnsupportedCapabilityError)


def test_the_style_manager_lists_one_kind_at_a_time(services: Services) -> None:
    everything = services.styles.list_styles()

    assert all(isinstance(entry, StyleEntry) for entry in everything)
    assert all(entry.kind in STYLE_MANAGER_KINDS for entry in everything)
    for kind in STYLE_MANAGER_KINDS:
        listed = services.styles.list_styles(kind)
        assert [entry.name for entry in listed] == [
            entry.name for entry in everything if entry.kind == kind
        ], kind
        assert all(entry.kind == kind for entry in listed)


def test_an_unknown_style_manager_kind_is_refused(services: Services) -> None:
    with pytest.raises(ValueError, match="style manager kind"):
        services.styles.list_styles("gradient")


def test_a_mesh_has_no_renderer_to_set(services: Services) -> None:
    if services.open_mesh is None:  # pragma: no cover - both backends have one
        pytest.skip("this backend does not open meshes")
    layer_id = services.open_mesh()

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as error:
        services.styles.symbology(layer_id)

    assert layer_id in str(error.value) or "mesh" in str(error.value)
