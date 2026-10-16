"""Behavior-readable scenarios for the optional Pydantic adapter seam."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict, cast

from contract_sample.pydantic_models import RunRequest, RunResult, RunResultReader
from jsonschema import Draft202012Validator
from pytest_bdd import given, parsers, scenarios, then, when
from qgis_sdk.adapters.pydantic import PydanticContractAdapter
from qgis_sdk.models import QgisSdkContractValidationError

scenarios("features/pydantic_contract.feature")

CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "qgis-sdk-bridge"
    / "tests"
    / "contracts"
    / "cases.json"
)


class SharedContractCase(TypedDict):
    name: str
    value: dict[str, object]


class SerializedRunResult(TypedDict):
    processed: int
    note: str | None


CASES: dict[str, SharedContractCase] = {
    case["name"]: cast(SharedContractCase, case)
    for case in json.loads(CASES_PATH.read_text(encoding="utf-8"))
}


@dataclass
class RunContract:
    adapter: PydanticContractAdapter[RunRequest, RunResultReader, RunResult]
    received: list[RunRequest] = field(default_factory=list)


@dataclass
class DispatchOutcome:
    result: SerializedRunResult | None = None
    error: QgisSdkContractValidationError | None = None


@given("the optional Pydantic run contract", target_fixture="contract")
def optional_run_contract() -> RunContract:
    received: list[RunRequest] = []

    def handler(request: RunRequest) -> RunResult:
        received.append(request)
        return RunResult(processed=request.count, note=request.label)

    adapter = PydanticContractAdapter(
        request_type=RunRequest,
        result_reader_type=RunResultReader,
        result_writer_type=RunResult,
        handler=handler,
    )
    return RunContract(adapter=adapter, received=received)


@when(
    parsers.parse('the shared request "{name}" is dispatched'),
    target_fixture="outcome",
)
def dispatch_shared_request(name: str, contract: RunContract) -> DispatchOutcome:
    payload = json.dumps(CASES[name]["value"])
    try:
        response = contract.adapter.handle_json(payload)
    except QgisSdkContractValidationError as error:
        return DispatchOutcome(error=error)
    return DispatchOutcome(result=cast(SerializedRunResult, json.loads(response)))


@then(
    parsers.parse(
        'the typed handler receives a request with mode "{mode}" and no label'
    )
)
def handler_receives_defaulted_request(mode: str, contract: RunContract) -> None:
    assert contract.received == [RunRequest("run", 2, mode=mode, label=None)]


@then("the serialized result includes its nullable default")
def result_includes_default(outcome: DispatchOutcome) -> None:
    assert outcome.result == {"processed": 2, "note": None}


@then("the serialized result satisfies the Pydantic writer schema")
def result_matches_writer_schema(
    outcome: DispatchOutcome, contract: RunContract
) -> None:
    assert outcome.result is not None
    assert Draft202012Validator(contract.adapter.result_writer_json_schema()).is_valid(
        outcome.result
    )


@then(parsers.parse('Pydantic reports a safe error path "{field}"'))
def validation_error_has_safe_path(field: str, outcome: DispatchOutcome) -> None:
    assert outcome.error is not None
    assert outcome.error.as_dict() == {
        "code": "contract_validation_failed",
        "direction": "request",
        "issues": [{"path": [field], "code": "int_type"}],
    }


@then("the typed handler is not called")
def invalid_request_does_not_dispatch(contract: RunContract) -> None:
    assert contract.received == []


@then("the reader schema accepts its named revision extension")
def reader_accepts_extension(contract: RunContract) -> None:
    schema = contract.adapter.result_reader_json_schema()
    assert Draft202012Validator(schema).is_valid({"processed": 2, "revision": "v2"})


@then("the writer schema rejects the reader-only revision")
def writer_rejects_extension(contract: RunContract) -> None:
    schema = contract.adapter.result_writer_json_schema()
    assert not Draft202012Validator(schema).is_valid(
        {"processed": 2, "note": None, "revision": "v2"}
    )


@then("the writer schema requires its serialized default")
def writer_requires_default(contract: RunContract) -> None:
    schema = contract.adapter.result_writer_json_schema()
    assert not Draft202012Validator(schema).is_valid({"processed": 2})


@then("the typed handler receives the normalized integer count 2")
def handler_receives_integral_float(contract: RunContract) -> None:
    assert contract.received == [RunRequest("run", 2)]
