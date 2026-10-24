"""Form rules: schema to widget family, and submitted values back to Python.

These tests are the whole reason the mapping lives outside the Qt adapter - they
pin the decisions (which widget, which coercion, which refusal) without a
display, and the adapter is then only allowed to be mechanical.
"""

from __future__ import annotations

import json

import pytest
from qgis_sdk.declarations import ActionDescription, action, describe_plugin, plugin
from qgis_sdk.models import QgisSdkFormError
from qgis_sdk.ui import FieldSpec, _coerce, coerce_values, form_fields


def _action(properties, required=(), action_id="demo.run"):
    request = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        request["required"] = list(required)
    return ActionDescription(
        id=action_id,
        title="Demo",
        handler="run_action",
        request=request,
        result={"type": "null"},
    )


def test_fields_follow_declaration_order_and_store_types() -> None:
    action = _action(
        {
            "name": {"type": "string"},
            "count": {"type": "integer"},
            "ratio": {"type": "number"},
            "enabled": {"type": "boolean"},
        }
    )

    specs = form_fields(action)

    assert [(spec.name, spec.widget) for spec in specs] == [
        ("name", "text"),
        ("count", "integer"),
        ("ratio", "number"),
        ("enabled", "boolean"),
    ]
    assert [spec.label for spec in specs] == ["Name", "Count", "Ratio", "Enabled"]


def test_a_marker_wins_over_the_stored_type() -> None:
    """A layer id and a note are both strings on the wire and different widgets."""
    action = _action(
        {
            "layer_id": {"type": "string"},
            "working_crs": {"type": "string"},
            "distance": {"type": "number"},
        }
    )

    specs = form_fields(
        action,
        markers={"layer_id": "layer", "working_crs": "crs", "distance": "metres"},
    )

    assert [spec.widget for spec in specs] == ["layer", "crs", "metres"]


def test_an_unknown_marker_is_refused_rather_than_ignored() -> None:
    action = _action({"layer_id": {"type": "string"}})

    with pytest.raises(QgisSdkFormError, match="unknown widget marker"):
        form_fields(action, markers={"layer_id": "combo"})


def test_an_enum_becomes_a_choice_carrying_its_options() -> None:
    action = _action({"mode": {"enum": ["fast", "safe"]}})

    (spec,) = form_fields(action)

    assert spec.widget == "choice"
    assert spec.choices == ("fast", "safe")


def test_a_nullable_field_is_optional_even_when_the_schema_requires_it() -> None:
    action = _action(
        {"note": {"anyOf": [{"type": "string"}, {"type": "null"}]}}, required=("note",)
    )

    (spec,) = form_fields(action)

    assert spec.nullable is True
    assert spec.required is False


def test_a_wide_union_has_no_single_widget_and_is_refused() -> None:
    action = _action({"either": {"anyOf": [{"type": "string"}, {"type": "integer"}]}})

    with pytest.raises(QgisSdkFormError, match="union field"):
        form_fields(action)


def test_a_schema_without_a_widget_is_refused() -> None:
    action = _action({"rows": {"type": "array", "items": {"type": "string"}}})

    with pytest.raises(QgisSdkFormError, match="no widget for schema"):
        form_fields(action)


def test_required_fields_are_marked_in_the_specification() -> None:
    action = _action(
        {"name": {"type": "string"}, "note": {"type": "string"}}, ("name",)
    )

    name, note = form_fields(action)

    assert name.required is True
    assert note.required is False


def test_coerce_returns_the_handler_types_not_the_widget_strings() -> None:
    action = _action(
        {
            "name": {"type": "string"},
            "count": {"type": "integer"},
            "ratio": {"type": "number"},
            "enabled": {"type": "boolean"},
            "mode": {"enum": ["fast", "safe"]},
        }
    )

    values = coerce_values(
        action,
        {
            "name": "  buffer ",
            "count": "3",
            "ratio": "1.5",
            "enabled": "TRUE",
            "mode": "safe",
        },
    )

    assert values == {
        "name": "buffer",
        "count": 3,
        "ratio": 1.5,
        "enabled": True,
        "mode": "safe",
    }


def test_coerce_keeps_integers_and_floats_distinct() -> None:
    action = _action({"count": {"type": "integer"}, "ratio": {"type": "number"}})

    values = coerce_values(action, {"count": 4, "ratio": 2})

    assert values == {"count": 4, "ratio": 2.0}
    assert isinstance(values["ratio"], float)
    assert isinstance(values["count"], int)


def test_coerce_passes_a_real_boolean_through_unchanged() -> None:
    action = _action({"enabled": {"type": "boolean"}})

    assert coerce_values(action, {"enabled": False}) == {"enabled": False}


def test_coerce_omits_optional_fields_that_were_not_submitted() -> None:
    action = _action(
        {"name": {"type": "string"}, "note": {"type": "string"}}, ("name",)
    )

    assert coerce_values(action, {"name": "x"}) == {"name": "x"}


def test_coerce_accepts_none_for_a_nullable_field() -> None:
    action = _action({"note": {"anyOf": [{"type": "string"}, {"type": "null"}]}})

    assert coerce_values(action, {"note": None}) == {"note": None}


def test_coerce_refuses_an_unknown_field() -> None:
    action = _action({"name": {"type": "string"}})

    with pytest.raises(QgisSdkFormError, match="no such field"):
        coerce_values(action, {"name": "x", "extra": 1})


def test_coerce_refuses_a_missing_required_field() -> None:
    action = _action({"name": {"type": "string"}}, ("name",))

    with pytest.raises(QgisSdkFormError, match="name is required"):
        coerce_values(action, {})


def test_coerce_refuses_an_empty_required_text_field() -> None:
    action = _action({"name": {"type": "string"}}, ("name",))

    with pytest.raises(QgisSdkFormError, match="non-empty string"):
        coerce_values(action, {"name": "   "})


@pytest.mark.parametrize(
    ("widget", "value", "expected"),
    [
        ({"name": {"type": "string"}}, 5, "a string"),
        ({"count": {"type": "integer"}}, "many", "an integer"),
        ({"count": {"type": "integer"}}, True, "a number"),
        ({"ratio": {"type": "number"}}, "1.5x", "a number"),
        ({"ratio": {"type": "number"}}, [1], "a number"),
        ({"enabled": {"type": "boolean"}}, "yes", "a boolean"),
        ({"mode": {"enum": ["fast"]}}, "slow", "one of"),
    ],
)
def test_coerce_refuses_a_value_it_cannot_convert(widget, value, expected) -> None:
    action = _action(widget)
    name = next(iter(widget))

    with pytest.raises(QgisSdkFormError, match=expected):
        coerce_values(action, {name: value})


def test_a_field_family_with_no_coercion_is_refused() -> None:
    """The spec is a closed vocabulary; an unknown family must not pass through."""
    spec = FieldSpec(name="name", label="Name", widget="canvas", required=True)

    with pytest.raises(QgisSdkFormError, match="renderable value"):
        _coerce("demo:run", spec, "x")


def test_a_field_spec_serializes_for_a_host() -> None:
    spec = FieldSpec(
        name="mode", label="Mode", widget="choice", required=True, choices=("a",)
    )

    assert spec.to_dict() == {
        "name": "mode",
        "label": "Mode",
        "widget": "choice",
        "required": True,
        "nullable": False,
        "choices": ["a"],
    }


def test_the_description_names_the_handler_instead_of_serializing_it() -> None:
    """A form dispatches by binding name, so no callable crosses the wire."""

    @plugin(id="demo.forms", title="Form demo")
    class Demo:
        @action(id="demo.plain", title="Plain fields")
        def plain(self, name: str) -> None:
            self.seen = name

    payload = describe_plugin(Demo).to_dict()

    assert payload["actions"][0]["handler"] == "plain"
    # A callable, a set or a non-finite float would break this round trip.
    assert json.loads(json.dumps(payload)) == payload
