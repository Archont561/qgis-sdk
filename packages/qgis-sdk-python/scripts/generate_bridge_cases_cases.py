"""Build the checked-in bridge cases that both languages validate (TASK-4).

The file is the contract fixture, not a snapshot: Python rebuilds it from the
dispatcher and refuses to drift from the checked-in copy, and the TypeScript
client parses the same replies and must reach the same verdict. That is what
"Python and TypeScript validate the same contract fixtures" means here - one
producer, two independent readers.

Regenerate with:

    python packages/qgis-sdk-python/scripts/generate_bridge_cases.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from generate_bridge_cases_hosts import (
    BRIDGE_PROTOCOL_VERSION,
    MAX_FRAMES_PER_PUMP,
    MAX_QUEUED_EVENTS,
    PUSHED,
    TICKS,
    FilePolicy,
    HandleKind,
    StreamEventType,
    _Clock,
    _host,
    deep,
    file_host,
    identity_host,
    record,
    request,
    stream_host,
    subscribe,
)


def _releasing_case(binding, cases, releasing):
    request = {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "kind": "release",
        "call_id": "case-release",
        "payload": {
            "handles": [
                {"kind": "borrowed", "id": "layer-1"},
                {"kind": "borrowed", "id": "layer-9"},
            ]
        },
    }
    reply = releasing.dispatch(binding, request)
    return _case_result(cases, reply, request)


def _case_result(cases, reply, request):
    cases.append(
        {
            "name": "release-borrowed",
            "request": request,
            "reply": reply,
            "expect": {"ok": True, "value": reply["value"]},
        }
    )

    return {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "cases": cases,
        "streams": _stream_cases(),
    }


def _stream_cases_phase1(binding, overflow, streams, subscription_id):
    streams.append(
        {
            "name": "gap-overflow",
            "frames": _drain(overflow, binding, subscription_id),
        }
    )

    return streams


def _basic_cases(cases: list[dict[str, Any]]) -> None:
    """The success, authorization and generation cases."""
    record(
        cases, "success", _host(), request("demo.echo", {"name": "A"}, "case-success")
    )
    record(
        cases,
        "unknown-operation",
        _host(),
        request("demo.missing", None, "case-unknown"),
    )
    record(
        cases,
        "not-authorized",
        _host(allow=False),
        request("demo.echo", None, "case-denied"),
    )
    record(
        cases,
        "stale-generation",
        _host(),
        request("demo.echo", None, "case-stale"),
        advance=True,
    )


def _malformed_cases(cases: list[dict[str, Any]]) -> None:
    """A bad protocol or a payload nested past the decoder's depth."""
    record(
        cases,
        "invalid-protocol",
        _host(),
        {
            "protocol": 99,
            "call_id": "case-protocol",
            "operation": "demo.echo",
            "payload": {},
        },
    )
    record(
        cases,
        "invalid-payload",
        _host(),
        request("demo.echo", {"nested": deep(40)}, "case-payload"),
    )


def _refusal_cases(cases: list[dict[str, Any]]) -> None:
    """Result kinds the dispatcher refuses, and a handler that fails."""
    record(
        cases,
        "not-serializable",
        _host(),
        request("demo.native", None, "case-native"),
    )
    record(
        cases,
        "operation-failed",
        _host(),
        request("demo.fails", None, "case-failed"),
    )
    record(
        cases,
        "invalid-result",
        _host(),
        request("demo.malformed", None, "case-invalid-result"),
    )


def _standard_cases(cases: list[dict[str, Any]]) -> None:
    """Every request shape that needs only the standard host."""
    _basic_cases(cases)
    _malformed_cases(cases)
    _refusal_cases(cases)


def _cancelled_case(cases: list[dict[str, Any]]) -> None:
    """A cancellation callback stops the dispatch before the handler runs."""
    cancelled = _host()
    binding = cancelled.bind(view_id="view-1", origin="qgis://desktop")
    reply = cancelled.dispatch(
        binding, request("demo.echo", None, "case-cancelled"), cancelled=lambda: True
    )
    cases.append(
        {
            "name": "cancelled",
            "request": request("demo.echo", None, "case-cancelled"),
            "reply": reply,
            "expect": {"ok": False, "code": reply["error"]["code"]},
        }
    )


def _forged_case(cases: list[dict[str, Any]]) -> None:
    """A page claiming another view never gets that view's identity."""
    forged = request("demo.whoami", {"view_id": "view-2"}, "case-forged")
    forged["view_id"] = "view-2"
    forged["generation"] = 99
    record(cases, "forged-identity", identity_host(), forged)


def _expired_handle_case(cases: list[dict[str, Any]]) -> None:
    """A file handle whose TTL elapsed is refused before the file is opened."""
    with tempfile.TemporaryDirectory() as directory:
        dataset = Path(directory) / "sites.geojson"
        dataset.write_text('{"type": "FeatureCollection", "features": []}')
        clock = _Clock()
        rig, authority = file_host(clock)
        binding = rig.bind(view_id="view-1", origin="qgis://desktop")
        ref = authority.grant_file(binding, dataset, FilePolicy(ttl_seconds=60))
        clock.now += 61
        expired = request("layers.open_vector", {"file": ref.to_wire()}, "case-expired")
        reply = rig.dispatch(binding, expired)
        cases.append(
            {
                "name": "expired-handle",
                "request": expired,
                "reply": reply,
                "expect": {"ok": False, "code": reply["error"]["code"]},
            }
        )


def _releasing_rig():
    """A host tracking one borrowed handle, ready for the release request."""
    releasing = _host()
    binding = releasing.bind(view_id="view-1", origin="qgis://desktop")
    releasing.track(binding, HandleKind.BORROWED, "layer-1")
    return binding, releasing


def build_cases() -> dict[str, Any]:
    """Return every case, built by running the real dispatcher."""
    cases: list[dict[str, Any]] = []
    _standard_cases(cases)
    _cancelled_case(cases)
    _forged_case(cases)
    _expired_handle_case(cases)
    binding, releasing = _releasing_rig()
    return _releasing_case(binding, cases, releasing)


def _ack_frame(host: Any, binding: Any, subscription_id: str, frame: dict) -> None:
    """Acknowledge one delivered frame through the dispatcher."""
    host.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": f"ack-{frame['seq']}",
            "kind": "ack",
            "subscription_id": subscription_id,
            "seq": frame["seq"],
        },
    )


def _drain(
    host: Any,
    binding: Any,
    subscription_id: str,
    *,
    limit: int = MAX_FRAMES_PER_PUMP,
    rounds: int = MAX_QUEUED_EVENTS + 2,
) -> list[dict[str, Any]]:
    """Collect a whole stream the way a protocol-2 client does: pump, then ack.

    The host hands out at most ``MAX_IN_FLIGHT_FRAMES`` unacknowledged frames, so
    a reader that only pumps would stop after eight and never see the terminal.
    Acknowledging each delivered frame through the dispatcher is also what keeps
    this fixture honest: the frames in the file are the ones a real client gets.
    """
    frames: list[dict[str, Any]] = []
    for _ in range(rounds):
        batch = host.pump(binding, limit=limit)
        if not batch:
            break
        frames.extend(batch)
        for frame in batch:
            if "terminal" in frame:
                continue
            _ack_frame(host, binding, subscription_id, frame)
        if any("terminal" in frame for frame in batch):
            break
    return frames


def _stream_cases() -> list[dict[str, Any]]:
    """Return the stream frames the TypeScript client has to reach too.

    The point is the same as for the replies: the frames are produced by the real
    dispatcher, so a change to ordering, terminal shapes or the gap rule fails on
    both sides until the fixture is regenerated.
    """
    streams: list[dict[str, Any]] = []

    ordered = stream_host()
    binding = ordered.bind(view_id="view-1", origin="qgis://desktop")
    subscribe(ordered, binding, TICKS.id)
    streams.append({"name": "ordered-complete", "frames": ordered.pump(binding)})

    coalesced = stream_host()
    binding = coalesced.bind(view_id="view-1", origin="qgis://desktop")
    subscription_id = subscribe(coalesced, binding, PUSHED.id)
    coalesced.emit(subscription_id, {"percent": 10}, kind=StreamEventType.PROGRESS)
    coalesced.emit(subscription_id, {"percent": 20}, kind=StreamEventType.PROGRESS)
    coalesced.emit(subscription_id, {"row": 1})
    streams.append({"name": "progress-coalesced", "frames": coalesced.pump(binding)})

    overflow = stream_host()
    binding = overflow.bind(view_id="view-1", origin="qgis://desktop")
    subscription_id = subscribe(overflow, binding, PUSHED.id)
    for index in range(MAX_QUEUED_EVENTS + 1):
        overflow.emit(subscription_id, {"index": index})
    return _stream_cases_phase1(binding, overflow, streams, subscription_id)
