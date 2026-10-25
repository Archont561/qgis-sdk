"""Keep the optional Pydantic schemas reproducible and aligned with shared cases."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from contract_sample.pydantic_export import build_schemas
from jsonschema import Draft202012Validator

# scripts/ sits beside tests/, so the project root is the test dir's grandparent.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# The sibling qgis-sdk-typescript package sits one level above the project root.
BRIDGE_CONTRACTS = PROJECT_ROOT.parent / "qgis-sdk-typescript" / "tests" / "contracts"
SCHEMAS_DIR = BRIDGE_CONTRACTS / "pydantic" / "generated" / "schemas"
CASES: list[dict[str, Any]] = json.loads(
    (BRIDGE_CONTRACTS / "cases.json").read_text(encoding="utf-8")
)


@pytest.fixture(scope="module")
def schemas() -> dict[str, dict[str, Any]]:
    return build_schemas()


def test_checked_in_pydantic_schemas_match_adapter(
    schemas: dict[str, dict[str, Any]],
) -> None:
    expected_files = {f"{name}.schema.json" for name in schemas}
    assert {path.name for path in SCHEMAS_DIR.glob("*.json")} == expected_files
    for name, schema in schemas.items():
        checked_in = json.loads(
            (SCHEMAS_DIR / f"{name}.schema.json").read_text(encoding="utf-8")
        )
        assert checked_in == schema
        Draft202012Validator.check_schema(schema)


def test_pydantic_schema_generation_is_deterministic(
    tmp_path: Path, schemas: dict[str, dict[str, Any]]
) -> None:
    exporter = PROJECT_ROOT / "scripts" / "generate_pydantic_contract.py"
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
def test_pydantic_generated_schemas_match_python_case_oracle(
    case: dict[str, Any], schemas: dict[str, dict[str, Any]]
) -> None:
    schema = schemas[f"pydantic-{case['schema']}"]
    assert Draft202012Validator(schema).is_valid(case["value"]) is case["valid"]
