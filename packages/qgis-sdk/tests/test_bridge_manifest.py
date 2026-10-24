"""One declared manifest drives the allowlist, the handshake and validation.

The tests here are about the promise decision-26 makes: what the plugin declares
is what the host advertises, what it accepts and what it will refuse. Nothing
needs Qt, QGIS or a browser, because the whole point is that a declared action's
schema is enough to check a call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pytest
from qgis_sdk.bridge import BridgeOperation, Dispatcher
from qgis_sdk.declarations import action, describe_plugin, plugin
from qgis_sdk.models.errors import QgisSdkBridgeError

ORIGIN = "qgis://desktop"


@dataclass(frozen=True)
class Summary:
    total: int
    largest: str


@plugin(id="org.example.sites", title="Sites")
class SitesPlugin:
    """A plugin whose whole bridge surface is its declarations."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @action(id="sites.summary", title="Summarize sites")
    def summarize(
        self,
        layer_id: str,
        limit: int = 10,
        mode: Literal["fast", "exact"] = "fast",
        label: str | None = None,
    ) -> Summary:
        self.calls.append(
            {"layer_id": layer_id, "limit": limit, "mode": mode, "label": label}
        )
        return Summary(total=2, largest=layer_id)

    @action(id="sites.broken", title="Return a malformed result")
    def broken(self, layer_id: str) -> Summary:
        return {"total": "many", "largest": layer_id}  # type: ignore[return-value]


def _host(*, allow: bool = True) -> tuple[Dispatcher, SitesPlugin]:
    instance = SitesPlugin()
    description = describe_plugin(SitesPlugin)
    handlers = {
        declared.id: getattr(instance, declared.handler)
        for declared in description.actions
    }
    dispatcher = Dispatcher.from_description(
        description,
        handlers,
        authorize=(lambda binding, operation: True) if allow else None,
    )
    return dispatcher, instance


def _call(
    operation: str, payload: dict[str, Any], call_id: str = "call-1"
) -> dict[str, Any]:
    return {
        "protocol": 1,
        "call_id": call_id,
        "operation": operation,
        "payload": payload,
    }


def test_the_allowlist_is_the_description_and_nothing_else() -> None:
    dispatcher, _ = _host()
    binding, reply = dispatcher.handshake(view_id="view-1", origin=ORIGIN)

    assert [operation.id for operation in dispatcher.operations()] == [
        "sites.broken",
        "sites.summary",
    ]
    # The handshake carries the same ids as the description it advertises.
    assert [operation["id"] for operation in reply["operations"]] == [
        declared["id"] for declared in reply["plugin"]["actions"]
    ]
    assert reply["operations"][1]["request"]["additionalProperties"] is False
    assert reply["operations"][1]["result"]["required"] == ["total", "largest"]
    assert reply["generation"] == binding.generation == 0


def test_a_declared_action_without_a_handler_is_refused_at_wiring_time() -> None:
    description = describe_plugin(SitesPlugin)

    with pytest.raises(QgisSdkBridgeError, match="sites.summary"):
        Dispatcher.from_description(
            description, {"sites.broken": lambda **kwargs: Summary(0, "")}
        )


def test_the_payload_arrives_as_keyword_arguments_and_defaults_apply() -> None:
    dispatcher, instance = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(
        binding, _call("sites.summary", {"layer_id": "sites", "limit": 25})
    )

    assert reply["ok"] is True
    assert reply["value"] == {"total": 2, "largest": "sites"}
    assert instance.calls == [
        {"layer_id": "sites", "limit": 25, "mode": "fast", "label": None}
    ]


def test_an_undeclared_argument_never_reaches_python() -> None:
    dispatcher, instance = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(
        binding, _call("sites.summary", {"layer_id": "sites", "extra": 1})
    )

    assert reply["ok"] is False
    assert reply["error"]["code"] == "invalid_payload"
    assert reply["error"]["message"] == "payload.extra: unknown property"
    assert instance.calls == []


def test_a_missing_required_argument_names_the_field() -> None:
    dispatcher, _ = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("sites.summary", {"limit": 5}))

    assert reply["error"]["code"] == "invalid_payload"
    assert reply["error"]["message"] == "payload.layer_id: required property is missing"


def test_a_wrongly_typed_argument_is_refused_with_its_path() -> None:
    dispatcher, _ = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("sites.summary", {"layer_id": 7}))

    assert (
        reply["error"]["message"] == "payload.layer_id: expected a string, got integer"
    )


def test_a_boolean_is_not_an_integer() -> None:
    dispatcher, _ = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(
        binding, _call("sites.summary", {"layer_id": "sites", "limit": True})
    )

    assert (
        reply["error"]["message"] == "payload.limit: expected an integer, got boolean"
    )


def test_an_integer_outside_the_safe_range_is_refused() -> None:
    dispatcher, _ = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(
        binding, _call("sites.summary", {"layer_id": "sites", "limit": 2**53})
    )

    assert reply["error"]["code"] == "invalid_payload"
    assert "above the maximum" in reply["error"]["message"]


def test_a_literal_is_checked_against_its_choices() -> None:
    dispatcher, _ = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(
        binding, _call("sites.summary", {"layer_id": "sites", "mode": "quick"})
    )

    assert reply["error"]["message"] == "payload.mode: expected one of 'fast', 'exact'"


def test_an_optional_argument_accepts_null_and_refuses_the_wrong_type() -> None:
    dispatcher, _ = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    accepted = dispatcher.dispatch(
        binding, _call("sites.summary", {"layer_id": "sites", "label": None})
    )
    refused = dispatcher.dispatch(
        binding, _call("sites.summary", {"layer_id": "sites", "label": 3})
    )

    assert accepted["ok"] is True
    assert refused["error"]["code"] == "invalid_payload"
    assert "matches none of the allowed forms" in refused["error"]["message"]


def test_a_nested_object_is_validated_field_by_field() -> None:
    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register(
        BridgeOperation(
            "demo.nested",
            "A nested request",
            request={
                "type": "object",
                "properties": {
                    "options": {
                        "type": "object",
                        "properties": {
                            "rows": {"type": "array", "items": {"type": "integer"}}
                        },
                        "required": ["rows"],
                        "additionalProperties": False,
                    }
                },
                "required": ["options"],
                "additionalProperties": False,
            },
        ),
        lambda payload: payload,
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(
        binding, _call("demo.nested", {"options": {"rows": [1, "two"]}})
    )

    assert reply["error"]["message"] == (
        "payload.options.rows[1]: expected an integer, got string"
    )


def test_a_declared_action_whose_result_breaks_the_schema_is_reported() -> None:
    dispatcher, _ = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("sites.broken", {"layer_id": "sites"}))

    assert reply["ok"] is False
    assert reply["error"]["code"] == "invalid_result"
    assert reply["error"]["message"] == "result.total: expected an integer, got string"


def test_a_result_may_carry_fields_the_schema_does_not_declare() -> None:
    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register(
        BridgeOperation(
            id="demo.additive",
            title="Return more than it promised",
            request={"type": "object", "properties": {}, "additionalProperties": False},
            result={
                "type": "object",
                "properties": {"total": {"type": "integer"}},
                "required": ["total"],
                "additionalProperties": False,
            },
        ),
        lambda payload: {"total": 1, "future": "ignored"},
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("demo.additive", {}))

    assert reply["ok"] is True
    assert reply["value"] == {"total": 1, "future": "ignored"}


def test_a_malformed_result_never_leaks_its_value() -> None:
    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register(
        BridgeOperation(
            id="demo.secret",
            title="Leak nothing",
            request={"type": "object", "properties": {}, "additionalProperties": False},
            result={"type": "object", "properties": {}, "required": ["token"]},
        ),
        lambda payload: {"value": "s3cr3t"},
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("demo.secret", {}))

    assert "s3cr3t" not in str(reply)
    assert reply["error"]["message"] == "result.token: required property is missing"


def test_a_schema_construct_outside_the_subset_is_refused_loudly() -> None:
    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register(
        BridgeOperation(
            "demo.ref",
            "A schema the SDK does not speak",
            request={
                "type": "object",
                "properties": {"x": {"$ref": "#/$defs/thing"}},
                "additionalProperties": False,
            },
        ),
        lambda payload: payload,
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("demo.ref", {"x": 1}))

    assert reply["error"]["code"] == "invalid_payload"
    assert "unsupported schema keyword(s) $ref" in reply["error"]["message"]


def test_an_operation_without_schemas_keeps_the_old_behaviour() -> None:
    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register(
        BridgeOperation("demo.plain", "No schema"), lambda payload: payload
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("demo.plain", {"anything": [1, 2]}))

    assert reply["ok"] is True
    assert reply["value"] == {"anything": [1, 2]}


def test_a_json_description_is_accepted_like_the_object() -> None:
    instance = SitesPlugin()
    description = describe_plugin(SitesPlugin).to_dict()
    dispatcher = Dispatcher.from_description(
        description,
        {"sites.summary": instance.summarize, "sites.broken": instance.broken},
        authorize=lambda binding, operation: True,
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("sites.summary", {"layer_id": "a"}))

    assert reply["ok"] is True
    assert [
        operation["id"]
        for operation in dispatcher.handshake(view_id="v", origin=ORIGIN)[1][
            "operations"
        ]
    ] == [
        "sites.broken",
        "sites.summary",
    ]


def test_from_runtime_reads_the_description_and_the_bound_handlers() -> None:
    instance = SitesPlugin()
    description = describe_plugin(SitesPlugin)

    class Runtime:
        def __init__(self) -> None:
            self.description = description
            self.actions = {
                "sites.summary": instance.summarize,
                "sites.broken": instance.broken,
            }

    dispatcher = Dispatcher.from_runtime(
        Runtime(), authorize=lambda binding, operation: True
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("sites.summary", {"layer_id": "a"}))

    assert reply["value"] == {"total": 2, "largest": "a"}
    assert instance.calls[0]["layer_id"] == "a"


def test_a_subscription_payload_is_validated_the_same_way() -> None:
    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register_stream(
        BridgeOperation(
            "demo.ticks",
            "Emit ticks",
            request={
                "type": "object",
                "properties": {"count": {"type": "integer"}},
                "required": ["count"],
                "additionalProperties": False,
            },
        ),
        lambda payload: iter([{"index": index} for index in range(payload["count"])]),
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    refused = dispatcher.dispatch(
        binding,
        {
            "protocol": 1,
            "kind": "subscribe",
            "call_id": "s1",
            "operation": "demo.ticks",
            "payload": {},
        },
    )
    accepted = dispatcher.dispatch(
        binding,
        {
            "protocol": 1,
            "kind": "subscribe",
            "call_id": "s2",
            "operation": "demo.ticks",
            "payload": {"count": 2},
        },
    )

    assert refused["error"]["code"] == "invalid_payload"
    assert refused["error"]["message"] == "payload.count: required property is missing"
    assert accepted["ok"] is True
    assert dispatcher.subscriptions() != ()


def test_an_input_that_is_not_a_python_name_is_refused_at_wiring_time() -> None:
    class Handler:
        def __call__(self, **kwargs: Any) -> Summary:
            return Summary(0, "")

    mapping = describe_plugin(SitesPlugin).to_dict()
    mapping["actions"][0]["request"] = {
        "type": "object",
        "properties": {"not a name": {"type": "string"}},
        "additionalProperties": False,
    }

    with pytest.raises(QgisSdkBridgeError, match="not a Python parameter name"):
        Dispatcher.from_description(
            mapping,
            {declared["id"]: Handler() for declared in mapping["actions"]},
        )


def test_an_operation_advertises_its_schemas_only_when_it_has_them() -> None:
    assert BridgeOperation("demo.plain", "Plain").to_dict() == {
        "id": "demo.plain",
        "title": "Plain",
    }

    described = BridgeOperation(
        "demo.typed",
        "Typed",
        request={"type": "object", "properties": {}, "additionalProperties": False},
        result={"type": "object", "properties": {"total": {"type": "integer"}}},
    ).to_dict()

    assert described["request"]["additionalProperties"] is False
    assert described["result"]["properties"]["total"] == {"type": "integer"}
