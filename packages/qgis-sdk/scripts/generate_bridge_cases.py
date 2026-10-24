#!/usr/bin/env python3
"""Build the checked-in bridge cases that both languages validate (TASK-4).

The file is the contract fixture, not a snapshot: Python rebuilds it from the
dispatcher and refuses to drift from the checked-in copy, and the TypeScript
client parses the same replies and must reach the same verdict. That is what
"Python and TypeScript validate the same contract fixtures" means here - one
producer, two independent readers.

Regenerate with:

    python packages/qgis-sdk/scripts/generate_bridge_cases.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
CASES_PATH = (
    REPOSITORY_ROOT
    / "packages"
    / "qgis-sdk-bridge"
    / "tests"
    / "contracts"
    / "bridge"
    / "cases.json"
)

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from qgis_sdk.bridge import (
    BRIDGE_PROTOCOL_VERSION,
    BridgeOperation,
    Dispatcher,
)
from qgis_sdk.bridge.streams import (
    MAX_QUEUED_EVENTS,
    StreamEventType,
)
from qgis_sdk.models import QgisSdkLayerNotFoundError

ECHO = BridgeOperation(id="demo.echo", title="Echo the payload")
TICKS = BridgeOperation(id="demo.ticks", title="A pulled stream of ticks")
PUSHED = BridgeOperation(id="demo.pushed", title="A stream the host pushes into")
FAILS = BridgeOperation(id="demo.fails", title="Fail with an SDK error")
NATIVE = BridgeOperation(id="demo.native", title="Return a value that cannot cross")


def _request(operation: str, payload: Any = None, call_id: str = "case") -> dict:
    return {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "call_id": call_id,
        "operation": operation,
        "payload": {} if payload is None else payload,
    }


def _stream_host() -> Dispatcher:
    """A host with one pulled stream and one pushed stream."""
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    dispatcher.register_stream(TICKS, lambda payload: iter([{"index": 0}, {"index": 1}]))
    dispatcher.register_stream(PUSHED, lambda payload: None)
    return dispatcher


def _subscribe(dispatcher: Dispatcher, binding, operation: str) -> str:
    reply = dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "subscribe",
            "call_id": "stream-case",
            "operation": operation,
            "payload": {},
        },
    )
    return reply["value"]["subscription_id"]


def _host(*, allow: bool = True) -> Dispatcher:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=(lambda binding, operation: True) if allow else None,
    )
    dispatcher.register(ECHO, lambda payload: {"echo": payload})
    dispatcher.register(FAILS, _raise_sdk_error)
    dispatcher.register(NATIVE, lambda payload: object())
    return dispatcher


def _raise_sdk_error(payload: Any) -> Any:
    raise QgisSdkLayerNotFoundError("sites")


def _deep(root: int) -> list:
    payload: list = []
    current = payload
    for _ in range(root):
        nested: list = []
        current.append(nested)
        current = nested
    return payload


def build_cases() -> dict[str, Any]:
    """Return every case, built by running the real dispatcher."""
    cases: list[dict[str, Any]] = []

    def record(
        name: str, dispatcher: Dispatcher, request: dict, *, advance: bool = False
    ) -> None:
        binding = dispatcher.bind(view_id="view-1", origin="qgis://desktop")
        if advance:
            dispatcher.advance_generation()
        reply = dispatcher.dispatch(binding, request)
        expect: dict[str, Any] = {"ok": reply["ok"]}
        if reply["ok"]:
            expect["value"] = reply["value"]
        else:
            expect["code"] = reply["error"]["code"]
        cases.append(
            {"name": name, "request": request, "reply": reply, "expect": expect}
        )

    record("success", _host(), _request("demo.echo", {"name": "A"}, "case-success"))
    record("unknown-operation", _host(), _request("demo.missing", None, "case-unknown"))
    record(
        "not-authorized", _host(allow=False), _request("demo.echo", None, "case-denied")
    )
    record(
        "stale-generation",
        _host(),
        _request("demo.echo", None, "case-stale"),
        advance=True,
    )
    record(
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
        "invalid-payload",
        _host(),
        _request("demo.echo", {"nested": _deep(40)}, "case-payload"),
    )
    record("not-serializable", _host(), _request("demo.native", None, "case-native"))
    record("operation-failed", _host(), _request("demo.fails", None, "case-failed"))

    cancelled = _host()
    binding = cancelled.bind(view_id="view-1", origin="qgis://desktop")
    reply = cancelled.dispatch(
        binding, _request("demo.echo", None, "case-cancelled"), cancelled=lambda: True
    )
    cases.append(
        {
            "name": "cancelled",
            "request": _request("demo.echo", None, "case-cancelled"),
            "reply": reply,
            "expect": {"ok": False, "code": reply["error"]["code"]},
        }
    )

    return {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "cases": cases,
        "streams": _stream_cases(),
    }


def _stream_cases() -> list[dict[str, Any]]:
    """Return the stream frames the TypeScript client has to reach too.

    The point is the same as for the replies: the frames are produced by the real
    dispatcher, so a change to ordering, terminal shapes or the gap rule fails on
    both sides until the fixture is regenerated.
    """
    streams: list[dict[str, Any]] = []

    ordered = _stream_host()
    binding = ordered.bind(view_id="view-1", origin="qgis://desktop")
    _subscribe(ordered, binding, TICKS.id)
    streams.append({"name": "ordered-complete", "frames": ordered.pump(binding)})

    coalesced = _stream_host()
    binding = coalesced.bind(view_id="view-1", origin="qgis://desktop")
    subscription_id = _subscribe(coalesced, binding, PUSHED.id)
    coalesced.emit(
        subscription_id, {"percent": 10}, kind=StreamEventType.PROGRESS
    )
    coalesced.emit(
        subscription_id, {"percent": 20}, kind=StreamEventType.PROGRESS
    )
    coalesced.emit(subscription_id, {"row": 1})
    streams.append(
        {"name": "progress-coalesced", "frames": coalesced.pump(binding)}
    )

    overflow = _stream_host()
    binding = overflow.bind(view_id="view-1", origin="qgis://desktop")
    subscription_id = _subscribe(overflow, binding, PUSHED.id)
    for index in range(MAX_QUEUED_EVENTS + 1):
        overflow.emit(subscription_id, {"index": index})
    streams.append(
        {
            "name": "gap-overflow",
            "frames": overflow.pump(binding, limit=MAX_QUEUED_EVENTS + 1),
        }
    )

    return streams


def main() -> int:
    cases = build_cases()
    CASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Tabs and sorted keys are what biome writes for the same file, so the
    # generator and the formatter do not fight over it on every run.
    CASES_PATH.write_text(
        json.dumps(cases, indent="\t", sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(cases['cases'])} cases to {CASES_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
