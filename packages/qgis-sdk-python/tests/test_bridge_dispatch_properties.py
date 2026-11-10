"""Properties of the endpoint's contract, for calls nobody wrote down.

``test_bridge_dispatch.py`` pins each refusal in isolation and
``test_bridge_streams_properties.py`` interleaves the stream state machine. What
is left is the promise that holds for *any* message a transport can hand the
dispatcher, whatever it declares and however malformed it is:

* every call is answered - with the call id it arrived with - and nothing raises
  into the transport, because an exception there loses the correlation and
  leaves the view waiting for a reply that never arrives;
* every reply is JSON-safe, since the boundary check has already run by then;
* an invocation runs its handler exactly once, and only when it succeeds - no
  refusal path reaches the handler, and no accepted call reaches it twice;
* a call is refused when its binding belongs to a replaced generation, for every
  kind, and no handler runs for it;
* an operation the allowlist does not hold is refused by name, not by accident.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
from qgis_sdk.bridge import BRIDGE_PROTOCOL_VERSION, BridgeOperation, Dispatcher
from qgis_sdk.bridge.endpoint._types import ViewBinding

ECHO = BridgeOperation(id="prop.echo", title="Echo")
STREAM = BridgeOperation(id="prop.stream", title="A stream")
VIEW = ViewBinding(view_id="view-1", origin="qgis://desktop", generation=0)
KINDS = ("invoke", "subscribe", "ack", "unsubscribe", "release", "handshake")
_NO_OP_KINDS = ("ack", "unsubscribe", "handshake")
"""The kinds a view is answered without holding a grant: none of them runs work."""

_VALUE = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=8),
    lambda child: (
        st.lists(child, max_size=2)
        | st.dictionaries(st.text("abc", max_size=3), child, max_size=2)
    ),
    max_leaves=3,
)
"""A value that is JSON-safe already, so a refusal can only be about the call."""

_PAYLOAD = st.dictionaries(st.text("abcde", min_size=1, max_size=4), _VALUE, max_size=3)
_CALL_ID = st.text("abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=12)
_OPERATION = st.sampled_from(
    ["prop.echo", "prop.stream", "prop.missing", "other.wrong"]
)
_SUBSCRIPTION_ID = st.text("0123456789", min_size=1, max_size=3).map(
    lambda text: f"s{text}"
)


def _allow(binding: ViewBinding, operation: str) -> bool:
    """An authorizer that grants everything the allowlist holds."""
    return True


def _deny(binding: ViewBinding, operation: str) -> bool:
    """An authorizer that grants nothing, the way a host starts out."""
    return False


@st.composite
def _calls(draw: st.DrawFn) -> dict[str, Any]:
    """One call, of a random kind, with the fields that kind carries."""
    kind = draw(st.sampled_from(KINDS))
    call: dict[str, Any] = {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "call_id": draw(_CALL_ID),
        "kind": kind,
    }
    if kind in ("invoke", "subscribe"):
        call["operation"] = draw(_OPERATION)
        call["payload"] = draw(_PAYLOAD)
    if kind in ("ack", "unsubscribe"):
        call["subscription_id"] = draw(_SUBSCRIPTION_ID)
    if kind == "ack":
        call["seq"] = draw(st.integers(min_value=0, max_value=5))
    if kind in ("release", "invoke"):
        call["payload"] = draw(_PAYLOAD)
    return call


@st.composite
def _invocations(draw: st.DrawFn) -> dict[str, Any]:
    """One invocation: the only kind that has a handler to reach."""
    return {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "call_id": draw(_CALL_ID),
        "operation": draw(_OPERATION),
        "payload": draw(_PAYLOAD),
    }


def _host(*, authorize: Any = _allow) -> tuple[Dispatcher, list[str]]:
    """A dispatcher holding one handler, and the log of what it was asked to run."""
    seen: list[str] = []

    def echo(payload: Mapping[str, Any]) -> Any:
        seen.append("echo")
        return {"value": payload.get("value")}

    dispatcher = Dispatcher(authorize=authorize)
    dispatcher.register(ECHO, echo)
    dispatcher.register_stream(STREAM, lambda payload: iter(()))
    return dispatcher, seen


@given(call=_calls())
@settings(max_examples=60, deadline=None)
def test_every_call_is_answered_with_the_call_id_it_arrived_with(
    call: dict[str, Any],
) -> None:
    dispatcher, _ = _host()
    reply = dispatcher.dispatch(_fresh(dispatcher), call)

    assert reply["protocol"] == BRIDGE_PROTOCOL_VERSION
    assert reply["call_id"] == call["call_id"]
    assert isinstance(reply["ok"], bool)


@given(call=_calls())
@settings(max_examples=60, deadline=None)
def test_every_reply_is_json_safe(call: dict[str, Any]) -> None:
    dispatcher, _ = _host()
    reply = dispatcher.dispatch(_fresh(dispatcher), call)

    assert json.loads(json.dumps(reply)) == reply


@given(call=_invocations())
@settings(max_examples=60, deadline=None)
def test_an_invocation_runs_its_handler_exactly_when_it_succeeds(
    call: dict[str, Any],
) -> None:
    dispatcher, seen = _host()
    reply = dispatcher.dispatch(_fresh(dispatcher), call)

    assert len(seen) == (1 if reply["ok"] else 0)


@given(call=_calls())
@settings(max_examples=60, deadline=None)
def test_a_stale_binding_is_refused_for_every_kind(call: dict[str, Any]) -> None:
    dispatcher, seen = _host()
    binding = _fresh(dispatcher)
    dispatcher.advance_generation()

    reply = dispatcher.dispatch(binding, call)

    assert reply["ok"] is False
    assert reply["error"]["code"] == "stale_generation"
    assert seen == []


@given(call=_calls())
@settings(max_examples=60, deadline=None)
def test_a_view_without_a_grant_runs_nothing(call: dict[str, Any]) -> None:
    """A denied view may close what it never held; it may not run anything.

    The no-op answers are deliberate: a closing UI disposes twice, and an
    acknowledgement for a stream that already ended is accepted. Everything that
    does work is refused, and no handler is reached either way.
    """
    dispatcher, seen = _host(authorize=_deny)
    reply = dispatcher.dispatch(_fresh(dispatcher), call)

    if call["kind"] not in _NO_OP_KINDS:
        assert reply["ok"] is False
        assert reply["error"]["code"] == "not_authorized"
    assert seen == []


@given(call=_invocations())
@settings(max_examples=40, deadline=None)
def test_an_operation_outside_the_allowlist_is_refused_by_name(
    call: dict[str, Any],
) -> None:
    dispatcher, seen = _host()
    unknown = {**call, "operation": "prop.missing"}

    reply = dispatcher.dispatch(_fresh(dispatcher), unknown)

    assert reply["ok"] is False
    assert reply["error"]["code"] == "unknown_operation"
    assert "prop.missing" in reply["error"]["message"]
    assert seen == []


def _fresh(dispatcher: Dispatcher) -> ViewBinding:
    """A binding minted by this dispatcher, at its current generation."""
    return dispatcher.bind(view_id=VIEW.view_id, origin=VIEW.origin)
