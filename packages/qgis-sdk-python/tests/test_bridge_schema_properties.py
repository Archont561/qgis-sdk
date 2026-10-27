"""The bridge's schema check agrees with a reference JSON Schema validator.

``qgis_sdk.bridge.schema.validate`` is a small hand-written subset of JSON
Schema because the runtime carries no dependencies. ``test_bridge_dispatch.py``
and friends pin each keyword by example; this module compares the subset with
``jsonschema``'s Draft 2020-12 validator on generated schemas and values so a
rule the subset gets wrong is found rather than guessed at:

* on the dialect the bridge actually emits (no floats, no ``pattern``) the two
  validators accept and refuse exactly the same values;
* the subset never accepts anything Draft 2020-12 refuses, floats included;
* the few places the subset is deliberately stricter than the draft are listed
  once, as examples, so a change there is a decision and not an accident.
"""

from __future__ import annotations

from typing import Any

import jsonschema
import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from qgis_sdk.bridge.schema import validate
from qgis_sdk.models.errors import QgisSdkBridgeError

# -- strategies -------------------------------------------------------------

#: Property names a describer would emit; short so counterexamples stay small.
names = st.from_regex(r"\A[a-z][a-z_]{0,3}\Z")

#: JSON scalars without floats: Draft 2020-12 says ``1.0`` is an integer and the
#: subset says it is not, so the equivalence dialect leaves floats out.
scalars = st.one_of(st.none(), st.booleans(), st.integers(-20, 20), st.text(max_size=4))


def _bounded(type_name: str) -> st.SearchStrategy[dict[str, Any]]:
    """A numeric schema with optional, consistently ordered bounds."""

    def build(low: int | None, span: int | None) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": type_name}
        if low is not None:
            schema["minimum"] = low
        if span is not None:
            schema["maximum"] = (low or 0) + span
        return schema

    return st.builds(
        build, st.none() | st.integers(-10, 10), st.none() | st.integers(0, 10)
    )


def _schemas(leaf: st.SearchStrategy[dict[str, Any]]) -> st.SearchStrategy[dict]:
    def extend(children: st.SearchStrategy[dict]) -> st.SearchStrategy[dict]:
        arrays = st.builds(lambda items: {"type": "array", "items": items}, children)
        objects = st.builds(
            lambda props, required, strict: {
                "type": "object",
                "properties": props,
                "required": [name for name in required if name in props],
                "additionalProperties": strict,
            },
            st.dictionaries(names, children, max_size=3),
            st.lists(names, max_size=3),
            st.booleans(),
        )
        any_of = st.builds(
            lambda branches: {"anyOf": branches},
            st.lists(children, min_size=1, max_size=3),
        )
        return arrays | objects | any_of

    return st.recursive(leaf, extend, max_leaves=6)


_LEAVES = st.one_of(
    st.sampled_from([{"type": "string"}, {"type": "boolean"}, {"type": "null"}]),
    _bounded("integer"),
    _bounded("number"),
    st.builds(
        lambda choices: {"enum": choices}, st.lists(scalars, min_size=1, max_size=3)
    ),
)

#: The dialect the bridge emits, minus floats and ``pattern``: here the subset
#: and the draft must agree exactly.
schemas = _schemas(_LEAVES)

values = st.recursive(
    scalars,
    lambda children: (
        st.lists(children, max_size=3) | st.dictionaries(names, children, max_size=3)
    ),
    max_leaves=8,
)

#: Values with floats as well, for the one-direction check.
wide_values = st.recursive(
    scalars | st.floats(allow_nan=False, allow_infinity=False),
    lambda children: (
        st.lists(children, max_size=3) | st.dictionaries(names, children, max_size=3)
    ),
    max_leaves=8,
)


# -- helpers ----------------------------------------------------------------


def _subset_accepts(value: Any, schema: dict) -> bool:
    try:
        validate(value, schema, path="payload")
    except QgisSdkBridgeError:
        return False
    return True


def _draft_accepts(value: Any, schema: dict) -> bool:
    return jsonschema.Draft202012Validator(schema).is_valid(value)


# -- properties -------------------------------------------------------------


@given(schema=schemas, value=values)
@settings(max_examples=150, deadline=None, derandomize=True)
@example(schema={"type": "integer", "minimum": 0, "maximum": 0}, value=0)
@example(schema={"enum": [1]}, value=True)
@example(schema={"enum": [True]}, value=1)
@example(
    schema={
        "type": "object",
        "properties": {"a": {"type": "null"}},
        "required": ["a"],
        "additionalProperties": False,
    },
    value={"b": None},
)
@example(schema={"anyOf": [{"type": "null"}, {"type": "string"}]}, value="")
def test_the_subset_and_draft_2020_12_agree_on_the_bridge_dialect(
    schema: dict, value: Any
) -> None:
    assert _subset_accepts(value, schema) == _draft_accepts(value, schema)


@given(schema=schemas, value=wide_values)
@settings(max_examples=150, deadline=None, derandomize=True)
@example(schema={"type": "number", "maximum": 1}, value=1.5)
@example(schema={"type": "integer"}, value=2.0)
def test_the_subset_never_accepts_what_draft_2020_12_refuses(
    schema: dict, value: Any
) -> None:
    """Soundness: a value that crossed the bridge is a valid instance everywhere."""
    if _subset_accepts(value, schema):
        assert _draft_accepts(value, schema)


@given(schema=schemas)
@settings(max_examples=100, deadline=None, derandomize=True)
def test_every_generated_schema_is_a_schema_the_draft_accepts(schema: dict) -> None:
    """The strategy emits real Draft 2020-12 schemas, or the comparison is moot."""
    jsonschema.Draft202012Validator.check_schema(schema)


# -- documented divergences --------------------------------------------------


@pytest.mark.parametrize(
    ("schema", "value", "why"),
    [
        ({"type": "integer"}, 1.0, "a float is never an integer on this bridge"),
        (
            {"type": "string", "pattern": "[0-9]+"},
            "a1",
            "pattern must match the whole value, not a substring",
        ),
    ],
)
def test_where_the_subset_is_stricter_than_the_draft_on_purpose(
    schema: dict, value: Any, why: str
) -> None:
    """Each row is accepted by Draft 2020-12 and refused here, by decision."""
    assert _draft_accepts(value, schema), why
    assert not _subset_accepts(value, schema), why


def test_a_tuple_crosses_as_an_array_because_handlers_return_them() -> None:
    """Python handlers return tuples; the draft has no such instance type."""
    assert _subset_accepts((1, 2), {"type": "array", "items": {"type": "integer"}})
