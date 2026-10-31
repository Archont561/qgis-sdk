"""One declared manifest drives the allowlist, the handshake and validation.

The tests here are about the promise decision-26 makes: what the plugin declares
is what the host advertises, what it accepts and what it will refuse. Nothing
needs Qt, QGIS or a browser, because the whole point is that a declared action's
schema is enough to check a call.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

import pytest
from qgis_sdk.bridge import BRIDGE_PROTOCOL_VERSION, BridgeOperation, Dispatcher
from qgis_sdk.declarations._describe import describe_plugin
from qgis_sdk.declarations._plugin import action, plugin, stream
from qgis_sdk.models import FileInput, FileRef
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
        "protocol": BRIDGE_PROTOCOL_VERSION,
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


def test_the_kind_annotation_is_not_an_unsupported_keyword() -> None:
    """The describer puts ``x-qgis-sdk`` on inputs; validation ignores it."""
    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register(
        BridgeOperation(
            "demo.paint",
            "An input with a kind",
            request={
                "type": "object",
                "properties": {
                    "fill": {"type": "string", "x-qgis-sdk": {"kind": "colour"}}
                },
                "required": ["fill"],
                "additionalProperties": False,
            },
        ),
        lambda payload: payload,
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("demo.paint", {"fill": "#ff0000"}))

    assert reply["ok"] is True
    assert reply["value"] == {"fill": "#ff0000"}


def test_a_file_input_reaches_the_handler_as_the_ref_the_host_minted() -> None:
    """A page sends the ``FileRef`` object; ``FileInput()`` receives a ``FileRef``."""
    received: list[object] = []

    @plugin(id="files", title="Files")
    class Files:
        @action
        def load(self, source: FileInput(filters=("*.csv",)), note: str = "") -> str:
            received.append(source)
            return source.name

    description = describe_plugin(Files)
    instance = Files()
    dispatcher = Dispatcher.from_description(
        description,
        {"load": instance.load},
        authorize=lambda binding, operation: True,
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = FileRef(id="a" * 16, name="lookup.csv", operations=("read",))

    reply = dispatcher.dispatch(binding, _call("load", {"source": ref.to_wire()}))

    assert reply["ok"] is True, reply
    assert reply["value"] == "lookup.csv"
    assert received == [ref]
    wrong_kind = {**ref.to_wire(), "kind": "folder"}
    refused = dispatcher.dispatch(binding, _call("load", {"source": wrong_kind}))
    assert refused["ok"] is False
    assert refused["error"]["code"] == "invalid_payload"


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
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "subscribe",
            "call_id": "s1",
            "operation": "demo.ticks",
            "payload": {},
        },
    )
    accepted = dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
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


# -- declared streams (decision-28) ---------------------------------------------


@dataclass(frozen=True)
class Change:
    layer_id: str
    count: int


@dataclass(frozen=True)
class Progress:
    done: int


@plugin(id="org.example.watch", title="Watch")
class WatchPlugin:
    """One action and one stream, declared side by side."""

    def __init__(self, items: list[Any] | None = None) -> None:
        self.items = items
        self.requests: list[dict[str, Any]] = []

    @action(id="sites.refresh", title="Refresh")
    def refresh(self) -> Summary:
        return Summary(total=0, largest="")

    @stream(
        id="sites.watch",
        title="Watch one layer",
        events={"data": Change, "progress": Progress},
    )
    def watch(self, layer_id: str, every: int = 1) -> Iterator[Any]:
        self.requests.append({"layer_id": layer_id, "every": every})
        if self.items is not None:
            yield from self.items
            return
        yield {"kind": "progress", "payload": Progress(done=0)}
        yield Change(layer_id=layer_id, count=every)


def _watch_host(items: list[Any] | None = None) -> tuple[Dispatcher, WatchPlugin]:
    instance = WatchPlugin(items)
    description = describe_plugin(WatchPlugin)
    dispatcher = Dispatcher.from_description(
        description,
        {"sites.refresh": instance.refresh},
        streams={"sites.watch": instance.watch},
        authorize=lambda binding, operation: True,
    )
    return dispatcher, instance


def _subscribe(dispatcher: Dispatcher, binding: Any, payload: dict[str, Any]) -> dict:
    return dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "subscribe",
            "call_id": "s1",
            "operation": "sites.watch",
            "payload": payload,
        },
    )


def test_a_declared_stream_is_allowlisted_and_advertised_with_its_events() -> None:
    dispatcher, _ = _watch_host()
    _, reply = dispatcher.handshake(view_id="view-1", origin=ORIGIN)

    advertised = {item["id"]: item for item in reply["operations"]}
    assert sorted(advertised) == ["sites.refresh", "sites.watch"]
    assert "result" not in advertised["sites.watch"]
    assert sorted(advertised["sites.watch"]["events"]) == ["data", "progress"]
    assert reply["plugin"]["streams"][0]["id"] == "sites.watch"


def test_a_declared_stream_without_a_factory_is_refused_at_wiring_time() -> None:
    instance = WatchPlugin()
    with pytest.raises(QgisSdkBridgeError, match="sites.watch.*no stream factory"):
        Dispatcher.from_description(
            describe_plugin(WatchPlugin), {"sites.refresh": instance.refresh}
        )


def test_a_stream_request_arrives_as_keyword_arguments_and_events_are_framed() -> None:
    dispatcher, instance = _watch_host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = _subscribe(dispatcher, binding, {"layer_id": "roads", "every": 3})
    frames = dispatcher.pump(binding)

    assert reply["ok"] is True
    assert instance.requests == [{"layer_id": "roads", "every": 3}]
    assert [frame.get("event", frame.get("terminal")) for frame in frames] == [
        {"kind": "progress", "payload": {"done": 0}},
        {"kind": "data", "payload": {"layer_id": "roads", "count": 3}},
        {"kind": "complete"},
    ]


def test_a_stream_request_is_strict_like_an_action_request() -> None:
    dispatcher, instance = _watch_host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    refused = _subscribe(dispatcher, binding, {"layer_id": "roads", "guess": True})

    assert refused["error"]["code"] == "invalid_payload"
    assert "guess" in refused["error"]["message"]
    assert instance.requests == []


def test_an_event_of_an_undeclared_kind_ends_the_stream_with_an_error() -> None:
    dispatcher, _ = _watch_host([{"kind": "state", "payload": {"done": 1}}])
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    _subscribe(dispatcher, binding, {"layer_id": "roads"})
    frames = dispatcher.pump(binding)

    assert [frame["terminal"]["kind"] for frame in frames] == ["error"]
    assert "'state'" in frames[0]["terminal"]["message"]
    assert "sites.watch" in frames[0]["terminal"]["message"]


def test_an_event_that_breaks_its_declared_schema_ends_the_stream() -> None:
    dispatcher, _ = _watch_host([Change(layer_id="roads", count="many")])  # type: ignore[arg-type]
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    _subscribe(dispatcher, binding, {"layer_id": "roads"})
    frames = dispatcher.pump(binding)

    assert frames[0]["terminal"]["kind"] == "error"
    assert "event.count" in frames[0]["terminal"]["message"]
    assert "many" not in frames[0]["terminal"]["message"]


def test_an_event_may_carry_fields_the_schema_does_not_declare() -> None:
    dispatcher, _ = _watch_host([{"layer_id": "roads", "count": 1, "extra": True}])
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    _subscribe(dispatcher, binding, {"layer_id": "roads"})
    frames = dispatcher.pump(binding)

    assert frames[0]["event"]["payload"]["extra"] is True
    assert frames[1]["terminal"]["kind"] == "complete"


def test_a_pushed_event_is_held_to_the_declaration_too() -> None:
    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register_stream(
        BridgeOperation(
            "demo.push",
            "Pushed",
            request={"type": "object", "properties": {}, "additionalProperties": False},
            events={
                "progress": {
                    "type": "object",
                    "properties": {"done": {"type": "integer"}},
                    "required": ["done"],
                }
            },
        ),
        lambda payload: None,
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    reply = dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "subscribe",
            "call_id": "s1",
            "operation": "demo.push",
            "payload": {},
        },
    )
    subscription_id = reply["value"]["subscription_id"]

    from qgis_sdk.bridge import StreamEventType

    assert dispatcher.emit(subscription_id, {"done": 1}, kind=StreamEventType.PROGRESS)
    assert not dispatcher.emit(subscription_id, {"done": 1}, kind=StreamEventType.DATA)
    frames = dispatcher.pump(binding)
    assert [frame.get("event", frame.get("terminal"))["kind"] for frame in frames] == [
        "progress",
        "error",
    ]


def test_an_operation_cannot_both_answer_and_stream() -> None:
    with pytest.raises(QgisSdkBridgeError, match="result or events, not both"):
        BridgeOperation(
            "demo.both",
            "Both",
            result={"type": "null"},
            events={"data": {"type": "null"}},
        )
    with pytest.raises(QgisSdkBridgeError, match="not a stream event kind"):
        BridgeOperation("demo.odd", "Odd", events={"ticks": {"type": "null"}})
    with pytest.raises(QgisSdkBridgeError, match="events must be a mapping"):
        BridgeOperation("demo.odd", "Odd", events=[("data", {"type": "null"})])  # type: ignore[arg-type]


def test_from_runtime_wires_the_bound_streams_as_well() -> None:
    instance = WatchPlugin()
    description = describe_plugin(WatchPlugin)

    class Runtime:
        def __init__(self) -> None:
            self.description = description
            self.actions = {"sites.refresh": instance.refresh}
            self.streams = {"sites.watch": instance.watch}

    dispatcher = Dispatcher.from_runtime(
        Runtime(), authorize=lambda binding, operation: True
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    assert _subscribe(dispatcher, binding, {"layer_id": "a"})["ok"] is True
    assert dispatcher.pump(binding)[-1]["terminal"] == {"kind": "complete"}
