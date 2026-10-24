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
from qgis_sdk.models import (
    QgisSdkBridgeError,
    QgisSdkError,
    QgisSdkLayerNotFoundError,
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
