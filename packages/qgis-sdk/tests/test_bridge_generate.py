"""The generator: deterministic output, a closed subset, and a drift check.

TASK-17 asks for three things, and each has a test here. The output is a pure
function of the description (AC 1); anything the generator cannot represent
fails instead of emitting a weaker type (AC 2 and 3); and a checked-in file can
be compared with a fresh run, which is what CI does (AC 3).

The generated module is exercised for real in ``packages/qgis-sdk-bridge``: a
test imports it and ``tsc`` compiles it, so "deterministic" here never becomes
"deterministic and useless".
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from contract_sample.bridge_plugin import SitesPlugin
from qgis_sdk.__main__ import app
from qgis_sdk.bridge.generate import (
    GENERATED_MARKER,
    check_generated,
    contract_fingerprint,
    describe_plugin_spec,
    generate_host_typescript,
    generate_typescript,
    load_description,
    write_generated,
)
from qgis_sdk.bridge.host import host_description
from qgis_sdk.declarations import describe_plugin
from qgis_sdk.models.errors import QgisSdkBridgeError
from typer.testing import CliRunner

runner = CliRunner()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = PROJECT_ROOT / "scripts" / "generate_bridge_clients.py"

SAMPLE = describe_plugin(SitesPlugin).to_dict()


def _generator():
    spec = importlib.util.spec_from_file_location("bridge_client_generator", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _description(**overrides: Any) -> dict[str, Any]:
    described = json.loads(json.dumps(SAMPLE))
    described.update(overrides)
    return described


def _actions(*, reverse: bool = False, **overrides: Any) -> dict[str, Any]:
    actions = json.loads(json.dumps(SAMPLE["actions"]))
    if reverse:
        actions.reverse()
    for action in actions:
        for key, value in overrides.items():
            action[key] = value
    return {
        "schema_version": 1,
        "id": "org.example.sites",
        "title": "Sites",
        "actions": actions,
    }


def _single(action_id: str, *, request: dict, result: dict) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": "org.example.sites",
        "title": "Sites",
        "actions": [
            {
                "id": action_id,
                "title": "One action",
                "handler": "run",
                "request": request,
                "result": result,
            }
        ],
    }


def test_generation_is_deterministic() -> None:
    first = generate_typescript(SAMPLE)
    second = generate_typescript(SAMPLE)
    assert first == second
    assert first.startswith(GENERATED_MARKER)
    assert first.endswith("\n")


def test_action_order_does_not_change_the_output() -> None:
    """The description's order is a declaration detail, not part of the contract."""
    assert generate_typescript(_description(actions=_actions()["actions"])) == (
        generate_typescript(_description(actions=_actions(reverse=True)["actions"]))
    )


def test_fingerprint_ignores_titles_and_handler_names() -> None:
    """A renamed Python method or a reworded label must not invalidate a client."""
    renamed = _actions(title="Something else", handler="renamed")
    assert contract_fingerprint(renamed) == contract_fingerprint(SAMPLE)


def test_fingerprint_tracks_the_wire_contract() -> None:
    changed = _actions()
    changed["actions"][0]["request"]["properties"]["layer_id"] = {"type": "integer"}
    assert contract_fingerprint(changed) != contract_fingerprint(SAMPLE)


def test_the_module_carries_every_declared_operation() -> None:
    generated = generate_typescript(SAMPLE)
    for action in SAMPLE["actions"]:
        assert f'"{action["id"]}"' in generated
    assert 'export const PLUGIN_ID = "org.example.sites";' in generated
    assert contract_fingerprint(SAMPLE) in generated
    assert "export function createOperations(" in generated
    assert "export class ContractError extends Error {" in generated
    assert "export type OperationId = (typeof OPERATIONS)[number];" in generated
    for action in SAMPLE["actions"]:
        assert f'\t"{action["id"]}",' in generated


def test_a_nested_object_becomes_a_named_interface_not_a_record() -> None:
    generated = generate_typescript(SAMPLE)
    assert "export interface SitesDetailsRequestOptions {" in generated
    assert "readonly options: SitesDetailsRequestOptions;" in generated
    assert 'SitesDetailsRequestOptions(value["options"], strict)' in generated


def test_a_non_object_result_validates_the_value_itself() -> None:
    """The request/result schema is not always an object, and the call must compile."""
    described = _single(
        "sites.count",
        request={"type": "object", "properties": {}, "additionalProperties": False},
        result={"type": "integer"},
    )
    generated = generate_typescript(described)
    assert "Promise<number>" in generated
    assert "isSafeInteger(value)" in generated


def test_unsupported_schema_keyword_is_refused() -> None:
    described = _single(
        "sites.ref",
        request={
            "type": "object",
            "properties": {"layer_id": {"$ref": "#/definitions/layer"}},
            "additionalProperties": False,
        },
        result={"type": "object", "properties": {}, "additionalProperties": False},
    )
    with pytest.raises(
        QgisSdkBridgeError, match=r"unsupported schema keyword\(s\) \$ref"
    ):
        generate_typescript(described)


def test_an_object_inside_a_union_is_refused() -> None:
    described = _single(
        "sites.mixed",
        request={
            "type": "object",
            "properties": {
                "which": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "object", "properties": {}},
                    ]
                }
            },
            "additionalProperties": False,
        },
        result={"type": "object", "properties": {}, "additionalProperties": False},
    )
    with pytest.raises(QgisSdkBridgeError, match="inside a union"):
        generate_typescript(described)


def test_duplicate_operation_ids_are_refused() -> None:
    described = _actions()
    described["actions"].append(json.loads(json.dumps(described["actions"][0])))
    with pytest.raises(QgisSdkBridgeError, match="duplicate action id"):
        generate_typescript(described)


def test_a_prefix_that_is_both_operation_and_namespace_is_refused() -> None:
    described = _single(
        "sites",
        request={"type": "object", "properties": {}, "additionalProperties": False},
        result={"type": "object", "properties": {}, "additionalProperties": False},
    )
    described["actions"].append(
        {
            "id": "sites.summary",
            "title": "Nested",
            "handler": "run",
            "request": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "result": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        }
    )
    with pytest.raises(QgisSdkBridgeError, match="conflicts with an action"):
        generate_typescript(described)


def test_an_action_without_declared_schemas_is_refused() -> None:
    described = _actions()
    del described["actions"][0]["request"]
    with pytest.raises(QgisSdkBridgeError, match="needs declared request and result"):
        generate_typescript(described)


def test_check_reports_a_missing_file(tmp_path: Path) -> None:
    message = check_generated(tmp_path / "missing.ts", SAMPLE)
    assert message is not None
    assert "does not exist" in message


def test_check_reports_drift_and_accepts_a_fresh_file(tmp_path: Path) -> None:
    target = tmp_path / "sites.ts"
    assert write_generated(target, SAMPLE) is True
    assert check_generated(target, SAMPLE) is None
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    message = check_generated(target, SAMPLE)
    assert message is not None
    assert "out of date" in message


def test_write_reports_whether_anything_changed(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "sites.ts"
    assert write_generated(target, SAMPLE) is True
    assert write_generated(target, SAMPLE) is False


def test_the_cli_reports_an_unimportable_module() -> None:
    result = runner.invoke(app, ["bridge", "generate", "--print", "--plugin", "x:Y"])
    assert result.exit_code == 1
    assert "cannot import" in result.output


def test_the_cli_describes_a_plugin_class_from_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The documented workflow: run it from the plugin's own root, no install."""
    monkeypatch.chdir(Path(__file__).parent)
    target = tmp_path / "sites.ts"
    result = runner.invoke(
        app,
        [
            "bridge",
            "generate",
            "--plugin",
            "contract_sample.bridge_plugin:SitesPlugin",
            "--out",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.output
    assert target.read_text(encoding="utf-8") == generate_typescript(SAMPLE)


def test_the_cli_needs_a_single_source(tmp_path: Path) -> None:
    both = runner.invoke(
        app,
        [
            "bridge",
            "generate",
            "--plugin",
            "x:Y",
            "--description",
            str(tmp_path / "d.json"),
            "--print",
        ],
    )
    assert both.exit_code == 1
    assert "exactly one of" in both.output
    neither = runner.invoke(app, ["bridge", "generate", "--print"])
    assert neither.exit_code == 1
    assert "exactly one of" in neither.output


def test_the_cli_needs_a_target(tmp_path: Path) -> None:
    described = tmp_path / "description.json"
    described.write_text(json.dumps(SAMPLE), encoding="utf-8")
    result = runner.invoke(app, ["bridge", "generate", "--description", str(described)])
    assert result.exit_code == 1
    assert "give --out, --check or --print" in result.output


def test_the_cli_round_trips_a_description_file(tmp_path: Path) -> None:
    described = tmp_path / "description.json"
    described.write_text(json.dumps(SAMPLE), encoding="utf-8")
    target = tmp_path / "sites.ts"

    wrote = runner.invoke(
        app,
        ["bridge", "generate", "--description", str(described), "--out", str(target)],
    )
    assert wrote.exit_code == 0, wrote.output
    assert wrote.output.strip() == f"wrote {target}"
    assert target.read_text(encoding="utf-8") == generate_typescript(SAMPLE)

    fresh = runner.invoke(
        app,
        [
            "bridge",
            "generate",
            "--description",
            str(described),
            "--check",
            "--out",
            str(target),
        ],
    )
    assert fresh.exit_code == 0, fresh.output
    assert "is up to date" in fresh.output

    target.write_text("// stale\n", encoding="utf-8")
    drifted = runner.invoke(
        app,
        [
            "bridge",
            "generate",
            "--description",
            str(described),
            "--check",
            "--out",
            str(target),
        ],
    )
    assert drifted.exit_code == 1
    assert "out of date" in drifted.output


def test_the_cli_prints_the_module_without_writing(tmp_path: Path) -> None:
    described = tmp_path / "description.json"
    described.write_text(json.dumps(SAMPLE), encoding="utf-8")
    result = runner.invoke(
        app, ["bridge", "generate", "--description", str(described), "--print"]
    )
    assert result.exit_code == 0, result.output
    assert result.output == generate_typescript(SAMPLE)
    assert list(tmp_path.iterdir()) == [described]


def test_describe_plugin_spec_reports_a_bad_spec() -> None:
    with pytest.raises(QgisSdkBridgeError, match="module:attribute"):
        describe_plugin_spec("contract_sample.bridge_plugin")
    with pytest.raises(QgisSdkBridgeError, match="has no attribute"):
        describe_plugin_spec("contract_sample.bridge_plugin:Missing")
    with pytest.raises(QgisSdkBridgeError, match="cannot import"):
        describe_plugin_spec("no_such_module_anywhere:SitesPlugin")


def test_load_description_reports_bad_input(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not-json", encoding="utf-8")
    with pytest.raises(QgisSdkBridgeError, match="is not JSON"):
        load_description(broken)
    listed = tmp_path / "list.json"
    listed.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(QgisSdkBridgeError, match="must contain a plugin description"):
        load_description(listed)
    with pytest.raises(QgisSdkBridgeError, match="cannot read"):
        load_description(tmp_path / "absent.json")


def test_the_checked_in_client_is_current() -> None:
    """CI owns the generated file: a stale copy fails here, on every host.

    Regenerating is a one-line command, so the failure message names it rather
    than leaving the reader to work out which script writes this file.
    """
    script = _generator()
    message = check_generated(script.PLUGIN_CLIENT_PATH, SAMPLE)
    assert message is None, (
        f"{message}; run `python packages/qgis-sdk/scripts/generate_bridge_clients.py`"
    )


# -- the host surface shares the renderer, not the identifiers --------------


def test_the_host_module_is_deterministic_and_names_its_own_surface() -> None:
    first = generate_host_typescript()
    assert first == generate_host_typescript(host_description())
    assert first.startswith(GENERATED_MARKER)
    assert 'export const HOST_ID = "qgis.host";' in first
    assert "export const HOST_SCHEMA_VERSION = 1;" in first
    assert "export const HOST_OPERATIONS = [" in first
    assert "export type HostOperationId =" in first
    assert "export interface HostOperations {" in first
    assert "export function createHost(" in first
    assert "export class HostContractError extends Error {" in first


def test_the_host_module_names_the_public_types_the_manifest_declared() -> None:
    generated = generate_host_typescript()
    assert "export interface VectorLayerInfo {" in generated
    assert "export interface LayerPage {" in generated
    assert "readonly items: readonly VectorLayerInfo[];" in generated
    assert "VectorLayerInfo(item, strict)" in generated
    # A tighter bound than the safe-integer range is enforced client-side too.
    assert 'value["limit"] >= 1 && value["limit"] <= 200' in generated


def test_the_two_surfaces_do_not_export_the_same_names() -> None:
    """A page imports both modules in one file, so the identifiers must differ."""
    plugin = generate_typescript(SAMPLE)
    host = generate_host_typescript()
    for name in (
        "PluginOperations",
        "createOperations",
        "ContractError",
        "BridgeClientLike",
        "OPERATIONS",
    ):
        assert (
            f"export interface {name}" in plugin
            or f"export class {name}" in plugin
            or (f"export const {name}" in plugin or f"export function {name}" in plugin)
        )
        assert f"export interface {name}" not in host
        assert f"export class {name}" not in host
        assert f"export const {name}" not in host
        assert f"export function {name}" not in host


def test_a_declared_name_wins_over_the_generated_one() -> None:
    described = _single(
        "sites.read",
        request={
            "type": "object",
            "properties": {"layer_id": {"type": "string"}},
            "required": ["layer_id"],
            "additionalProperties": False,
        },
        result={"type": "object", "properties": {}, "additionalProperties": False},
    )
    described["actions"][0]["result_name"] = "ReadingResult"
    described["actions"][0]["request_name"] = "ReadingRequest"
    generated = generate_typescript(described)
    assert "export interface ReadingResult {" in generated
    assert "export interface ReadingRequest {" in generated
    assert "Promise<ReadingResult>" in generated


def test_a_non_object_result_is_validated_by_an_inline_predicate() -> None:
    """`call` takes a function, so a bare schema has to arrive as one."""
    described = _single(
        "sites.ping",
        request={"type": "object", "properties": {}, "additionalProperties": False},
        result={"type": "null"},
    )
    generated = generate_typescript(described)
    assert "Promise<null>" in generated
    assert "(candidate: unknown) => candidate === null" in generated


def test_the_checked_in_host_client_is_current() -> None:
    script = _generator()
    message = check_generated(
        script.HOST_CLIENT_PATH, host_description(), generate=generate_host_typescript
    )
    assert message is None, (
        f"{message}; run `python packages/qgis-sdk/scripts/generate_bridge_clients.py`"
    )


def test_the_cli_renders_the_host_surface(tmp_path: Path) -> None:
    target = tmp_path / "host.ts"
    wrote = runner.invoke(app, ["bridge", "generate", "--host", "--out", str(target)])
    assert wrote.exit_code == 0, wrote.output
    assert target.read_text(encoding="utf-8") == generate_host_typescript()

    fresh = runner.invoke(
        app, ["bridge", "generate", "--host", "--check", "--out", str(target)]
    )
    assert fresh.exit_code == 0, fresh.output
    assert "is up to date" in fresh.output


def test_the_cli_refuses_to_mix_the_host_surface_with_a_plugin() -> None:
    result = runner.invoke(
        app, ["bridge", "generate", "--host", "--plugin", "x:Y", "--print"]
    )
    assert result.exit_code == 1
    assert "give no --plugin or --description" in result.output
