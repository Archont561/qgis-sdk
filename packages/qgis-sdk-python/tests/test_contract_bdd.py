"""Author-readable behavior for the checked request/result schema example."""

import json
from pathlib import Path
from typing import Any

from contract_sample.export import build_schemas
from contract_sample.models import RunRequest
from jsonschema import Draft202012Validator
from mashumaro.codecs.json import JSONDecoder
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/contract_wire.feature")

CASE_PATH = (
    Path(__file__).resolve().parents[2]
    / "qgis-sdk-typescript"
    / "tests"
    / "contracts"
    / "cases.json"
)
CASES = {
    case["name"]: case for case in json.loads(CASE_PATH.read_text(encoding="utf-8"))
}


@given("the generated sample wire schemas", target_fixture="validators")
def generated_schemas() -> dict[str, Draft202012Validator]:
    return {
        name: Draft202012Validator(schema) for name, schema in build_schemas().items()
    }


@when(
    parsers.parse('the shared payload "{name}" is validated'), target_fixture="accepted"
)
def check_payload(name: str, validators: dict[str, Draft202012Validator]) -> bool:
    case: dict[str, Any] = CASES[name]
    return validators[case["schema"]].is_valid(case["value"])


@then("the schema accepts it")
def accepted_payload(accepted: bool) -> None:
    assert accepted


@then("the schema rejects it")
def rejected_payload(accepted: bool) -> None:
    assert not accepted


@when(
    parsers.parse('the same shared payload "{name}" is decoded without validation'),
    target_fixture="decoded_request",
)
def decode_without_validation(name: str) -> RunRequest:
    return JSONDecoder(RunRequest).decode(json.dumps(CASES[name]["value"]))


@then("the default decoder nevertheless constructs a request with count 2")
def decoder_is_not_strict(decoded_request: RunRequest) -> None:
    assert decoded_request == RunRequest("run", 2)
