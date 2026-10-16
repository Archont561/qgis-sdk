"""Durable tests for the optional end-to-end controlled-deployment slice."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from contract_sample.pydantic_export import build_adapter
from contract_sample.pydantic_models import RunRequest, RunResult
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from qgis_sdk.adapters.pydantic_types import MAX_SAFE_INTEGER
from qgis_sdk.models import QgisSdkContractValidationError

CONTRACTS_PATH = (
    Path(__file__).resolve().parents[2]
    / "qgis-sdk-bridge"
    / "tests"
    / "contracts"
    / "cases.json"
)
CASES: list[dict[str, Any]] = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
REQUEST_CASES = [case for case in CASES if case["schema"] == "run-request"]


def test_shared_request_cases_match_strict_pydantic_validation() -> None:
    adapter = build_adapter()

    for case in REQUEST_CASES:
        payload = json.dumps(case["value"])
        if case["valid"]:
            request = adapter.validate_request_json(payload)
            assert type(request) is RunRequest
            assert request.kind == "run"
            assert request.count == int(case["value"]["count"])
        else:
            with pytest.raises(QgisSdkContractValidationError) as caught:
                adapter.validate_request_json(payload)
            assert caught.value.direction == "request"


def test_malformed_json_returns_a_safe_root_path() -> None:
    adapter = build_adapter()
    payload = '{"kind":"run","count":"private-malformed-value'

    with pytest.raises(QgisSdkContractValidationError) as caught:
        adapter.validate_request_json(payload)

    assert caught.value.issues[0].path == ()
    assert caught.value.issues[0].code == "json_invalid"
    assert "private-malformed-value" not in str(caught.value)
    assert "private-malformed-value" not in json.dumps(caught.value.as_dict())


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_numbers_are_rejected_at_the_integer_path(token: str) -> None:
    adapter = build_adapter()

    with pytest.raises(QgisSdkContractValidationError) as caught:
        adapter.validate_request_json(f'{{"kind":"run","count":{token}}}')

    assert caught.value.direction == "request"
    assert caught.value.issues[0].path == ("count",)


def test_defaulted_and_nullable_request_fields_remain_distinct() -> None:
    adapter = build_adapter()

    omitted = adapter.validate_request_json('{"kind":"run","count":2}')
    explicit_null = adapter.validate_request_json(
        '{"kind":"run","count":2,"label":null}'
    )

    assert omitted == RunRequest("run", 2, mode="safe", label=None)
    assert explicit_null == RunRequest("run", 2, mode="safe", label=None)
    with pytest.raises(QgisSdkContractValidationError) as caught:
        adapter.validate_request_json('{"kind":"run","count":2,"mode":null}')
    assert caught.value.issues[0].path == ("mode",)


def test_validation_error_has_safe_structured_path_without_input_value() -> None:
    adapter = build_adapter()
    sensitive_value = "private-request-value-9137"

    with pytest.raises(QgisSdkContractValidationError) as caught:
        adapter.validate_request_json(
            json.dumps({"kind": "run", "count": sensitive_value})
        )

    assert caught.value.as_dict() == {
        "code": "contract_validation_failed",
        "direction": "request",
        "issues": [{"path": ["count"], "code": "int_type"}],
    }
    assert sensitive_value not in str(caught.value)
    assert sensitive_value not in json.dumps(caught.value.as_dict())


def test_unknown_request_field_error_does_not_expose_its_value() -> None:
    adapter = build_adapter()
    sensitive_value = "do-not-echo-this-token"

    with pytest.raises(QgisSdkContractValidationError) as caught:
        adapter.validate_request_json(
            json.dumps({"kind": "run", "count": 2, "token": sensitive_value})
        )

    assert caught.value.issues[0].path == ("token",)
    assert caught.value.issues[0].code == "unexpected_keyword_argument"
    assert sensitive_value not in str(caught.value)
    assert sensitive_value not in json.dumps(caught.value.as_dict())


def test_reader_and_writer_schemas_keep_compatible_extensions_separate() -> None:
    adapter = build_adapter()
    reader = Draft202012Validator(adapter.result_reader_json_schema())
    writer = Draft202012Validator(adapter.result_writer_json_schema())

    assert reader.is_valid({"processed": 2, "revision": "v2"})
    assert not writer.is_valid({"processed": 2, "revision": "v2", "note": None})
    assert reader.is_valid({"processed": 2})
    assert not writer.is_valid({"processed": 2})


def test_handler_result_is_serialized_with_defaulted_nullable_fields() -> None:
    adapter = build_adapter()

    encoded = adapter.handle_json('{"kind":"run","count":3}')
    decoded = json.loads(encoded)

    assert decoded == {"processed": 3, "note": None}
    assert Draft202012Validator(adapter.result_writer_json_schema()).is_valid(decoded)


def test_invalid_handler_result_has_a_safe_result_error() -> None:
    adapter = build_adapter(handler=lambda _request: object())

    with pytest.raises(QgisSdkContractValidationError) as caught:
        adapter.handle_json('{"kind":"run","count":3}')

    assert caught.value.direction == "result"
    assert caught.value.code == "contract_validation_failed"
    assert caught.value.issues


@given(
    count=st.integers(min_value=-MAX_SAFE_INTEGER, max_value=MAX_SAFE_INTEGER),
    integral_float=st.booleans(),
    mode=st.sampled_from(("safe", "fast")),
    label=st.one_of(
        st.none(),
        st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=16),
    ),
)
@settings(max_examples=80, deadline=None, derandomize=True)
def test_hypothesis_valid_requests_reach_typed_handler_and_match_schemas(
    count: int, integral_float: bool, mode: str, label: str | None
) -> None:
    received: list[RunRequest] = []

    def handler(request: RunRequest) -> RunResult:
        received.append(request)
        return RunResult(processed=request.count, note=request.label)

    adapter = build_adapter(handler=handler)
    wire_count = float(count) if integral_float else count
    payload_value = {
        "kind": "run",
        "count": wire_count,
        "mode": mode,
        "label": label,
    }
    original = copy.deepcopy(payload_value)
    payload = json.dumps(payload_value)

    encoded_result = adapter.handle_json(payload)
    decoded_result = json.loads(encoded_result)

    assert payload_value == original
    assert received == [RunRequest("run", count, mode=mode, label=label)]
    assert decoded_result == {"processed": count, "note": label}
    assert Draft202012Validator(adapter.request_json_schema()).is_valid(payload_value)
    assert Draft202012Validator(adapter.result_writer_json_schema()).is_valid(
        decoded_result
    )


@given(magnitude=st.integers(min_value=MAX_SAFE_INTEGER + 1), negative=st.booleans())
@settings(max_examples=60, deadline=None, derandomize=True)
def test_hypothesis_unsafe_integer_is_rejected_at_the_count_path(
    magnitude: int, negative: bool
) -> None:
    count = -magnitude if negative else magnitude

    with pytest.raises(QgisSdkContractValidationError) as caught:
        build_adapter().validate_request_json(
            json.dumps({"kind": "run", "count": count})
        )

    assert caught.value.direction == "request"
    assert caught.value.issues[0].path == ("count",)
    assert str(count) not in json.dumps(caught.value.as_dict())


@given(
    secret=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=24
    )
)
@settings(max_examples=60, deadline=None, derandomize=True)
def test_hypothesis_invalid_scalar_is_rejected_without_echoing_raw_input(
    secret: str,
) -> None:
    adapter = build_adapter()
    sensitive_value = f"private-value-{secret}"
    payload = json.dumps({"kind": "run", "count": sensitive_value})

    with pytest.raises(QgisSdkContractValidationError) as caught:
        adapter.validate_request_json(payload)

    assert caught.value.direction == "request"
    assert caught.value.issues[0].path == ("count",)
    assert sensitive_value not in str(caught.value)
    assert sensitive_value not in json.dumps(caught.value.as_dict())
