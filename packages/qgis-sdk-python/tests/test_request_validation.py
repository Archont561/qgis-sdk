"""Characterize the existing test-only decoder/schema seam, not an SDK backend.

These counterexamples must survive backend deliberations: schema generation and
successful dataclass construction are not evidence of strict request validation.
"""

import copy
import json

import pytest
from contract_sample.export import build_schemas
from contract_sample.models import RunRequest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from mashumaro.codecs.json import JSONDecoder

REQUEST_SCHEMA = Draft202012Validator(build_schemas()["run-request"])
DECODER = JSONDecoder(RunRequest)


@given(count=st.integers(min_value=-1_000_000, max_value=1_000_000))
@settings(max_examples=80, deadline=None)
def test_default_decoder_coerces_numeric_strings_rejected_by_schema(count: int) -> None:
    payload = {"kind": "run", "count": str(count)}
    assert not REQUEST_SCHEMA.is_valid(payload)
    assert DECODER.decode(json.dumps(payload)) == RunRequest("run", count)


@given(
    extra=st.text(min_size=1).filter(
        lambda name: name not in {"kind", "count", "mode", "label"}
    )
)
@settings(max_examples=80, deadline=None)
def test_default_decoder_discards_unknown_fields_rejected_by_schema(extra: str) -> None:
    payload = {"kind": "run", "count": 2, extra: "unrecognized"}
    assert not REQUEST_SCHEMA.is_valid(payload)
    assert DECODER.decode(json.dumps(payload)) == RunRequest("run", 2)


@given(
    count=st.integers(min_value=-1_000_000, max_value=1_000_000),
    label=st.one_of(st.none(), st.text()),
    include_defaults=st.booleans(),
)
@settings(max_examples=80, deadline=None)
def test_validating_request_does_not_insert_defaults_or_mutate_payload(
    count: int, label: str | None, include_defaults: bool
) -> None:
    payload = {"kind": "run", "count": count}
    if include_defaults:
        payload.update(mode="safe", label=label)
    original = copy.deepcopy(payload)
    REQUEST_SCHEMA.validate(payload)
    assert payload == original
    assert DECODER.decode(json.dumps(payload)) == RunRequest(
        "run", count, label=label if include_defaults else None
    )


@pytest.mark.parametrize(("count", "coerced"), [(True, 1), (False, 0), (2.5, 2)])
def test_default_decoder_also_coerces_boolean_and_fractional_counts(
    count: object, coerced: int
) -> None:
    payload = {"kind": "run", "count": count}
    assert not REQUEST_SCHEMA.is_valid(payload)
    decoded = DECODER.decode(json.dumps(payload))
    assert type(decoded.count) is int
    assert decoded.count == coerced


def test_json_schema_integer_is_not_a_python_token_type_policy() -> None:
    # ADR-22 explicitly accepts integral JSON-number values, not only int tokens.
    assert REQUEST_SCHEMA.is_valid({"kind": "run", "count": 2.0})


@given(count=st.integers(min_value=-9007199254740991, max_value=9007199254740991))
@settings(max_examples=80, deadline=None)
def test_safe_integral_values_are_accepted_regardless_of_python_numeric_type(
    count: int,
) -> None:
    assert REQUEST_SCHEMA.is_valid({"kind": "run", "count": count})
    assert REQUEST_SCHEMA.is_valid({"kind": "run", "count": float(count)})


@given(magnitude=st.integers(min_value=9007199254740992), negative=st.booleans())
@settings(max_examples=80, deadline=None)
def test_unsafe_integers_are_rejected(magnitude: int, negative: bool) -> None:
    count = -magnitude if negative else magnitude
    assert not REQUEST_SCHEMA.is_valid({"kind": "run", "count": count})


@pytest.mark.parametrize("count", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_values_are_not_wire_integers(count: float) -> None:
    assert not REQUEST_SCHEMA.is_valid({"kind": "run", "count": count})
