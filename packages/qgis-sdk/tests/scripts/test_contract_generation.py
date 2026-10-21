"""A checked, QGIS-free schema/type contract example, not an SDK decoder."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from contract_sample.export import build_schemas
from contract_sample.models import RunResult
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from mashumaro.codecs.json import JSONEncoder

# scripts/ sits beside tests/, so the project root is the test dir's grandparent.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# The sibling qgis-sdk-bridge package sits one level above the project root.
BRIDGE_CONTRACTS = PROJECT_ROOT.parent / "qgis-sdk-bridge" / "tests" / "contracts"
SCHEMAS_DIR = BRIDGE_CONTRACTS / "generated" / "schemas"
CASES: list[dict[str, Any]] = json.loads(
    (BRIDGE_CONTRACTS / "cases.json").read_text(encoding="utf-8")
)


@pytest.fixture(scope="module")
def schemas() -> dict[str, dict[str, Any]]:
    return build_schemas()


def test_checked_in_schemas_match_python_dataclasses(
    schemas: dict[str, dict[str, Any]],
) -> None:
    expected_files = {f"{name}.schema.json" for name in schemas}
    assert {path.name for path in SCHEMAS_DIR.glob("*.json")} == expected_files
    for name, schema in schemas.items():
        assert (
            json.loads(
                (SCHEMAS_DIR / f"{name}.schema.json").read_text(encoding="utf-8")
            )
            == schema
        )
        Draft202012Validator.check_schema(schema)


def test_schema_export_is_deterministic_outside_the_workspace(
    tmp_path: Path, schemas: dict[str, dict[str, Any]]
) -> None:
    exporter = PROJECT_ROOT / "scripts" / "generate_contract.py"
    command = [sys.executable, str(exporter), str(tmp_path)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    first = {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}
    subprocess.run(command, check=True, capture_output=True, text=True)
    second = {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}
    assert first == second
    assert set(first) == {f"{name}.schema.json" for name in schemas}
    for name, content in first.items():
        assert content == (SCHEMAS_DIR / name).read_bytes(), f"stale schema: {name}"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_python_schema_accepts_only_the_shared_cases(
    case: dict[str, Any], schemas: dict[str, dict[str, Any]]
) -> None:
    validate = Draft202012Validator(schemas[case["schema"]]).is_valid
    assert validate(case["value"]) is case["valid"]


@given(
    processed=st.integers(min_value=0, max_value=1_000_000),
    note=st.one_of(
        st.none(),
        st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=12),
    ),
)
@settings(max_examples=80, deadline=None)
def test_serialized_python_result_matches_the_writer_contract(
    processed: int, note: str | None, schemas: dict[str, dict[str, Any]]
) -> None:
    value = json.loads(JSONEncoder(RunResult).encode(RunResult(processed, note)))
    assert value == {"processed": processed, "note": note}
    assert Draft202012Validator(schemas["run-result-writer"]).is_valid(value)
