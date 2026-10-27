"""Bridge dispatch: allowlist, trusted view identity, generations, safe replies.

The point of these tests is that the whole host side of the transport is
QGIS-free: envelopes in, dicts out. What a Qt adapter still has to do is carry
bytes and mint a binding, and neither of those decisions is testable in a unit
test that pretends to be a browser.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from qgis_sdk.bridge import (
    BRIDGE_PROTOCOL_VERSION,
    BridgeErrorCode,
    BridgeOperation,
    Dispatcher,
    to_wire,
)
from qgis_sdk.bridge.schema import validate
from qgis_sdk.models import (
    QgisSdkBridgeError,
    QgisSdkBridgeRefusalError,
    QgisSdkError,
    QgisSdkGrantRefusedError,
    QgisSdkLayerNotFoundError,
    QgisSdkStaleHandleError,
    QgisSdkUnknownHandleError,
)

ECHO = BridgeOperation(id="demo.echo", title="Echo the payload")
FAILS = BridgeOperation(id="demo.fails", title="Fail on purpose")


class Host:
    """A dispatcher with one echo operation and one that always fails."""

    def __init__(self, *, allow: bool = True) -> None:
        self.seen: list[tuple[str, str]] = []
        self.received: list[dict[str, Any]] = []
        self.dispatcher = Dispatcher(
            description={"schema_version": 1, "id": "demo.plugin", "actions": []},
            authorize=self._authorize if allow else None,
        )
        self.dispatcher.register(ECHO, self._echo)
        self.dispatcher.register(FAILS, self._fail)

    def _authorize(self, binding, operation: str) -> bool:
        self.seen.append((binding.view_id, operation))
        return True

    def _echo(self, payload):
        self.received.append(dict(payload))
        return {"echo": payload}

    def _fail(self, payload):
        raise QgisSdkLayerNotFoundError("sites")


def _invoke(operation: str, payload: dict[str, Any] | None = None, call_id="call-1"):
    return {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "call_id": call_id,
        "operation": operation,
        "payload": payload or {},
    }


def test_handshake_binds_the_view_and_advertises_the_contract() -> None:
    host = Host()

    binding, reply = host.dispatcher.handshake(
        view_id="view-1", origin="qgis://desktop"
    )

    assert binding.view_id == "view-1"
    assert binding.generation == 0
    assert reply["protocol"] == BRIDGE_PROTOCOL_VERSION
    assert reply["generation"] == 0
    assert reply["plugin"]["id"] == "demo.plugin"
    assert [operation["id"] for operation in reply["operations"]] == [
        "demo.echo",
        "demo.fails",
    ]
    # The handshake is a message like any other: it has to be sendable.
    assert json.loads(json.dumps(reply)) == reply


def test_a_view_can_ask_for_the_handshake_over_the_wire() -> None:
    """``kind: "handshake"`` answers a bound view with the advertised contract.

    A page that connects through QWebChannel is bound by the host before it
    says anything, so it needs a call - not a second binding - to learn what
    this view may use (TASK-66 AC #5).
    """
    host = Host()
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    reply = host.dispatcher.dispatch(
        binding,
        {"protocol": BRIDGE_PROTOCOL_VERSION, "call_id": "hello", "kind": "handshake"},
    )

    assert reply["ok"] is True
    assert reply["call_id"] == "hello"
    value = reply["value"]
    assert value["protocol"] == BRIDGE_PROTOCOL_VERSION
    assert value["generation"] == 0
    assert value["plugin"]["id"] == "demo.plugin"
    assert value["host_schema_version"] >= 1
    assert [operation["id"] for operation in value["operations"]] == [
        "demo.echo",
        "demo.fails",
    ]
    assert json.loads(json.dumps(reply)) == reply


def test_the_wire_handshake_advertises_only_what_the_view_may_call() -> None:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "actions": []},
        authorize=lambda binding, operation: operation == "demo.echo",
    )
    dispatcher.register(ECHO, lambda payload: payload)
    dispatcher.register(FAILS, lambda payload: payload)
    binding = dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    reply = dispatcher.dispatch(
        binding,
        {"protocol": BRIDGE_PROTOCOL_VERSION, "call_id": "hello", "kind": "handshake"},
    )

    assert [operation["id"] for operation in reply["value"]["operations"]] == [
        "demo.echo"
    ]


def test_the_wire_handshake_refuses_a_stale_generation() -> None:
    host = Host()
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")
    host.dispatcher.advance_generation()

    reply = host.dispatcher.dispatch(
        binding,
        {"protocol": BRIDGE_PROTOCOL_VERSION, "call_id": "hello", "kind": "handshake"},
    )

    assert reply["ok"] is False
    assert reply["error"]["code"] == BridgeErrorCode.STALE_GENERATION.value


def test_an_allowlisted_operation_runs_and_returns_its_value() -> None:
    host = Host()
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    reply = host.dispatcher.dispatch(binding, _invoke("demo.echo", {"name": "A"}))

    assert reply == {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "call_id": "call-1",
        "ok": True,
        "value": {"echo": {"name": "A"}},
    }
    assert host.received == [{"name": "A"}]


def test_an_unknown_operation_is_refused_by_code() -> None:
    host = Host()
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    reply = host.dispatcher.dispatch(binding, _invoke("demo.missing"))

    assert reply["ok"] is False
    assert reply["error"]["code"] == BridgeErrorCode.UNKNOWN_OPERATION.value
    assert "demo.missing" in reply["error"]["message"]


def test_a_view_without_a_grant_learns_nothing_about_the_allowlist() -> None:
    """Denying first is what stops a refusal from becoming a directory listing."""
    host = Host(allow=False)
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    known = host.dispatcher.dispatch(binding, _invoke("demo.echo"))
    unknown = host.dispatcher.dispatch(binding, _invoke("demo.missing"))

    assert known["error"]["code"] == BridgeErrorCode.NOT_AUTHORIZED.value
    assert unknown["error"]["code"] == BridgeErrorCode.NOT_AUTHORIZED.value


def test_authorization_sees_the_trusted_binding_not_the_payload() -> None:
    host = Host()
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    reply = host.dispatcher.dispatch(
        binding,
        _invoke("demo.echo", {"view_id": "admin", "generation": 99, "name": "A"}),
    )

    assert reply["ok"] is True
    assert host.seen == [("view-1", "demo.echo")]
    # The claims are payload, and payload is passed through as data.
    assert host.received == [{"view_id": "admin", "generation": 99, "name": "A"}]


def test_a_binding_from_a_retired_generation_is_refused() -> None:
    host = Host()
    stale = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    host.dispatcher.advance_generation()
    rejected = host.dispatcher.dispatch(stale, _invoke("demo.echo"))

    assert rejected["error"]["code"] == BridgeErrorCode.STALE_GENERATION.value

    fresh = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")
    assert host.dispatcher.dispatch(fresh, _invoke("demo.echo"))["ok"] is True


@pytest.mark.parametrize("payload", [{"callback": print}, {"nested": [[object()]]}])
def test_a_payload_that_cannot_cross_the_wire_is_refused(payload) -> None:
    host = Host()
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    reply = host.dispatcher.dispatch(binding, _invoke("demo.echo", payload))

    assert reply["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value
    assert host.received == []


def test_a_handler_result_that_cannot_cross_the_wire_is_refused() -> None:
    """The refusal names the type; the object itself never reaches the reply."""
    host = Host()
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")
    host.dispatcher.register(
        BridgeOperation(id="demo.native", title="Return a native object"),
        lambda payload: object(),
    )

    reply = host.dispatcher.dispatch(binding, _invoke("demo.native"))

    assert reply["error"]["code"] == BridgeErrorCode.NOT_SERIALIZABLE.value
    assert "object" in reply["error"]["message"]


def test_an_expected_failure_is_forwarded_with_its_code() -> None:
    host = Host()
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    reply = host.dispatcher.dispatch(binding, _invoke("demo.fails"))

    assert reply["error"]["code"] == BridgeErrorCode.OPERATION_FAILED.value
    assert "No layer 'sites'" in reply["error"]["message"]


def test_an_unexpected_failure_is_not_forwarded_verbatim() -> None:
    host = Host()
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    def explode(payload):
        raise RuntimeError("/home/user/secret/qgis.qgs is not readable")

    host.dispatcher.register(BridgeOperation(id="demo.boom", title="Boom"), explode)

    reply = host.dispatcher.dispatch(binding, _invoke("demo.boom"))

    assert reply["error"]["code"] == BridgeErrorCode.OPERATION_FAILED.value
    assert "secret" not in json.dumps(reply)


def test_a_cancelled_call_never_reaches_the_handler() -> None:
    host = Host()
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    reply = host.dispatcher.dispatch(
        binding, _invoke("demo.echo"), cancelled=lambda: True
    )

    assert reply["error"]["code"] == BridgeErrorCode.CANCELLED.value
    assert host.received == []


def test_an_unsupported_protocol_keeps_the_call_id_it_can_read() -> None:
    host = Host()
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")
    envelope = _invoke("demo.echo")
    envelope["protocol"] = BRIDGE_PROTOCOL_VERSION + 1

    reply = host.dispatcher.dispatch(binding, envelope)

    assert reply["call_id"] == "call-1"
    assert reply["error"]["code"] == BridgeErrorCode.INVALID_MESSAGE.value
    assert "protocol" in reply["error"]["message"]


def test_an_envelope_without_a_usable_call_id_is_still_answered() -> None:
    host = Host()
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")
    envelope = _invoke("demo.echo")
    envelope["call_id"] = ""

    reply = host.dispatcher.dispatch(binding, envelope)

    assert reply["call_id"] == ""
    assert reply["error"]["code"] == BridgeErrorCode.INVALID_MESSAGE.value


def test_duplicate_ids_are_refused_at_registration() -> None:
    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register(ECHO, lambda payload: None)

    with pytest.raises(QgisSdkBridgeError, match="duplicate operation id"):
        dispatcher.register(ECHO, lambda payload: None)


@pytest.mark.parametrize("bad_id", ["", "1demo", "demo/echo", "demo echo"])
def test_operation_ids_must_be_declarable(bad_id) -> None:
    with pytest.raises(QgisSdkBridgeError, match="Invalid operation id"):
        BridgeOperation(id=bad_id, title="Broken")


def test_the_wire_copy_is_a_copy() -> None:
    """A view can never hold a reference into the host's own structures."""
    original = {"items": [{"id": "a"}]}

    copy = to_wire(original)

    assert copy == original
    assert copy is not original
    assert copy["items"][0] is not original["items"][0]


def test_a_generic_sdk_error_is_forwarded_by_its_code() -> None:
    def refuse(payload):
        raise QgisSdkError("the host said no")

    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register(BridgeOperation(id="demo.refuse", title="Refuse"), refuse)
    binding = dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    reply = dispatcher.dispatch(binding, _invoke("demo.refuse"))

    assert reply["error"] == {
        "code": BridgeErrorCode.OPERATION_FAILED.value,
        "message": "the host said no",
    }


def test_a_declared_string_pattern_matches_the_whole_value() -> None:
    """`pattern` is part of the subset, and it means fullmatch, not search."""
    schema = {
        "type": "object",
        "properties": {"cursor": {"type": "string", "pattern": "[0-9]+"}},
        "additionalProperties": False,
    }
    validate({"cursor": "12"}, schema, path="payload")
    validate({}, schema, path="payload")
    for bad in ("abc", "-1", "1 ", "", "12a"):
        with pytest.raises(QgisSdkBridgeError, match="pattern"):
            validate({"cursor": bad}, schema, path="payload")


def test_a_pattern_that_is_not_a_string_is_refused() -> None:
    schema = {"type": "string", "pattern": 7}
    with pytest.raises(QgisSdkBridgeError, match="pattern must be a string"):
        validate("12", schema, path="payload")


# -- bound handlers and refusals the operation itself raises (TASK-20) --------


BOUND = BridgeOperation(id="demo.whoami", title="Tell the caller who it is")


def test_a_bound_handler_receives_the_host_minted_binding_not_a_claim() -> None:
    """A handler that needs the caller gets the binding the host minted."""
    host = Host()
    host.dispatcher.register_bound(
        BOUND, lambda binding, payload: {"view": binding.view_id, "got": payload}
    )
    binding = host.dispatcher.bind(view_id="view-7", origin="qgis://desktop")

    reply = host.dispatcher.dispatch(
        binding, _invoke("demo.whoami", {"view_id": "view-1", "x": 1})
    )

    assert reply["ok"] is True
    assert reply["value"] == {"view": "view-7", "got": {"view_id": "view-1", "x": 1}}


def test_register_bound_refuses_duplicates_and_non_callables() -> None:
    host = Host()
    with pytest.raises(QgisSdkBridgeError, match="duplicate"):
        host.dispatcher.register_bound(ECHO, lambda binding, payload: None)
    with pytest.raises(QgisSdkBridgeError, match="callable"):
        host.dispatcher.register_bound(BOUND, None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (
            QgisSdkUnknownHandleError("file ref f-1 is not one of this view's"),
            "unknown_handle",
        ),
        (QgisSdkStaleHandleError("file ref f-1 was revoked"), "stale_handle"),
        (QgisSdkGrantRefusedError("write is not granted"), "grant_refused"),
    ],
)
def test_a_refusal_an_operation_raises_keeps_its_own_code(
    error: QgisSdkBridgeRefusalError, code: str
) -> None:
    """A handle or grant refusal is a contract code, not an opaque failure."""
    host = Host()

    def refuse(payload):
        raise error

    host.dispatcher.register(BOUND, refuse)
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    reply = host.dispatcher.dispatch(binding, _invoke("demo.whoami"))

    assert reply["ok"] is False
    assert reply["error"] == {"code": code, "message": str(error)}
    assert BridgeErrorCode(code).value == code


def test_a_refusal_raised_by_a_stream_factory_keeps_its_code_too() -> None:
    host = Host()

    def refuse(payload):
        raise QgisSdkGrantRefusedError("origin is not granted")

    host.dispatcher.register_stream(BOUND, refuse)
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    reply = host.dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "subscribe",
            "call_id": "sub-1",
            "operation": "demo.whoami",
            "payload": {},
        },
    )

    assert reply["ok"] is False
    assert reply["error"]["code"] == "grant_refused"


# -- push sources: a stream the host feeds without knowing the id ------------


class _Fetch:
    """A source that starts work when attached and reports through the sink."""

    def __init__(self) -> None:
        self.sink = None
        self.closed = False

    def start(self, sink) -> None:
        self.sink = sink

    def close(self) -> None:
        self.closed = True


def _subscribe(dispatcher, binding, operation: str) -> dict[str, Any]:
    return dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "subscribe",
            "call_id": "sub-1",
            "operation": operation,
            "payload": {},
        },
    )


def test_a_push_source_is_started_with_a_sink_and_wakes_the_view() -> None:
    host = Host()
    fetch = _Fetch()
    host.dispatcher.register_bound_stream(BOUND, lambda binding, payload: fetch)
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")
    woken: list[str] = []
    host.dispatcher.watch(binding, lambda: woken.append(binding.view_id))

    reply = _subscribe(host.dispatcher, binding, "demo.whoami")

    assert reply["ok"] is True
    assert fetch.sink is not None
    assert woken == []
    assert fetch.sink.emit({"status": 200}) is True
    assert woken == ["view-1"]
    fetch.sink.complete()
    frames = host.dispatcher.pump(binding)
    assert [frame.get("event", frame.get("terminal")) for frame in frames] == [
        {"kind": "data", "payload": {"status": 200}},
        {"kind": "complete"},
    ]
    assert woken == ["view-1", "view-1"]
    # The sink is inert once the subscription ended: no exception, no frame.
    assert fetch.sink.emit({"status": 500}) is False
    assert fetch.closed is True


def test_a_push_source_fails_its_stream_with_the_sdk_message() -> None:
    host = Host()
    fetch = _Fetch()
    host.dispatcher.register_stream(BOUND, lambda payload: fetch)
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")
    _subscribe(host.dispatcher, binding, "demo.whoami")

    fetch.sink.fail(QgisSdkLayerNotFoundError("sites"))
    (frame,) = host.dispatcher.pump(binding)

    assert frame["terminal"]["kind"] == "error"
    assert "sites" in frame["terminal"]["message"]


def test_disposing_a_pushed_stream_closes_its_source() -> None:
    host = Host()
    fetch = _Fetch()
    host.dispatcher.register_stream(BOUND, lambda payload: fetch)
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")
    reply = _subscribe(host.dispatcher, binding, "demo.whoami")

    host.dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "unsubscribe",
            "call_id": "unsub",
            "subscription_id": reply["value"]["subscription_id"],
        },
    )

    assert fetch.closed is True
    assert fetch.sink.emit({"late": True}) is False


def test_unwatch_stops_the_wake_calls_and_a_wake_never_raises_into_the_host() -> None:
    host = Host()
    fetch = _Fetch()
    host.dispatcher.register_stream(BOUND, lambda payload: fetch)
    binding = host.dispatcher.bind(view_id="view-1", origin="qgis://desktop")
    woken: list[int] = []
    host.dispatcher.watch(binding, lambda: woken.append(1))
    _subscribe(host.dispatcher, binding, "demo.whoami")
    host.dispatcher.unwatch(binding)

    assert fetch.sink.emit({"n": 1}) is True
    assert woken == []


def test_the_handshake_carries_the_theme_the_provider_reads() -> None:
    palettes = [
        {"palette": {"window": "#323232"}, "dark": True},
        None,
        {"palette": {"window": "#efefef"}, "dark": False},
    ]
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "actions": []},
        authorize=lambda binding, operation: True,
        theme=lambda: palettes.pop(0),
    )

    binding, first = dispatcher.handshake(view_id="view-1", origin="qgis://desktop")
    assert first["theme"] == {"palette": {"window": "#323232"}, "dark": True}

    without = dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": "no-theme",
            "kind": "handshake",
        },
    )
    assert "theme" not in without["value"]

    again = dispatcher.dispatch(
        binding,
        {"protocol": BRIDGE_PROTOCOL_VERSION, "call_id": "theme", "kind": "handshake"},
    )
    assert again["value"]["theme"] == {"palette": {"window": "#efefef"}, "dark": False}
    assert json.loads(json.dumps(again)) == again


def test_a_dispatcher_without_a_provider_advertises_no_theme() -> None:
    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    _binding, reply = dispatcher.handshake(view_id="view-1", origin="qgis://desktop")
    assert "theme" not in reply
