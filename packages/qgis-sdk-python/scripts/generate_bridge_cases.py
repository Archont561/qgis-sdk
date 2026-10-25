#!/usr/bin/env python3
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

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
CASES_PATH = (
    REPOSITORY_ROOT
    / "packages"
    / "qgis-sdk-typescript"
    / "tests"
    / "contracts"
    / "bridge"
    / "cases.json"
)

sys.path.insert(0, str(PROJECT_ROOT.parent / "qgis-sdk-tools" / "src"))
sys.path.insert(0, str(PROJECT_ROOT.parent / "qgis-sdk-runtime" / "src"))

from qgis_sdk.bridge import (
    BRIDGE_PROTOCOL_VERSION,
    BridgeOperation,
    Dispatcher,
    ViewBinding,
)
from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.bridge.host import HostServices, register_host_operations
from qgis_sdk.bridge.resources import HandleKind
from qgis_sdk.bridge.streams import (
    MAX_QUEUED_EVENTS,
    StreamEventType,
)
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import QgisSdkLayerNotFoundError
from qgis_sdk.testing import (
    FakeLayers,
    FakeProject,
    FakeSettings,
    FakeStyles,
    RecordingNotifications,
)

ECHO = BridgeOperation(id="demo.echo", title="Echo the payload")
TICKS = BridgeOperation(id="demo.ticks", title="A pulled stream of ticks")
PUSHED = BridgeOperation(id="demo.pushed", title="A stream the host pushes into")
FAILS = BridgeOperation(id="demo.fails", title="Fail with an SDK error")
NATIVE = BridgeOperation(id="demo.native", title="Return a value that cannot cross")
MALFORMED = BridgeOperation(
    id="demo.malformed",
    title="Break its declared result",
    request={"type": "object", "properties": {}, "additionalProperties": False},
    result={
        "type": "object",
        "properties": {"total": {"type": "integer"}},
        "required": ["total"],
        "additionalProperties": False,
    },
)
WHOAMI = BridgeOperation(id="demo.whoami", title="Report who the host says is calling")

# A fixed token keeps the expired-handle case reproducible: the ref id would
# otherwise be fresh randomness on every run and the fixture could never match.
FIXED_TOKEN = "0123456789abcdef0123456789abcdef"


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
    dispatcher.register_stream(
        TICKS, lambda payload: iter([{"index": 0}, {"index": 1}])
    )
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
    dispatcher.register(MALFORMED, lambda payload: {"total": "many"})
    return dispatcher


def _raise_sdk_error(payload: Any) -> Any:
    raise QgisSdkLayerNotFoundError("sites")


def _whoami(binding: ViewBinding, payload: Any) -> dict[str, Any]:
    """Answer with the identity the host minted, never the one the page sent."""
    return {"view_id": binding.view_id, "generation": binding.generation}


def _identity_host() -> Dispatcher:
    dispatcher = _host()
    dispatcher.register_bound(WHOAMI, _whoami)
    return dispatcher


class _Clock:
    """A clock the case advances by hand, so an expiry is a fact and not a sleep."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _file_host(clock: _Clock) -> tuple[Dispatcher, HostAuthority]:
    """A host carrying only ``layers.open_vector`` over a clock the case controls."""
    scope = ResourceScope()
    layers = FakeLayers(scope)
    authority = HostAuthority(clock=clock, token=lambda: FIXED_TOKEN)
    services = HostServices(
        layers=layers,
        project=FakeProject(layers, scope),
        settings=FakeSettings(scope),
        styles=FakeStyles(layers, scope),
        notifications=RecordingNotifications(scope),
        authority=authority,
    )
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    register_host_operations(dispatcher, services, only=("layers.open_vector",))
    return dispatcher, authority


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
    record(
        "invalid-result",
        _host(),
        _request("demo.malformed", None, "case-invalid-result"),
    )

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

    # A page claiming to be another view, in the envelope and in the payload:
    # the host-minted binding answers and the claim is not even an error.
    forged = _request("demo.whoami", {"view_id": "view-2"}, "case-forged")
    forged["view_id"] = "view-2"
    forged["generation"] = 99
    record("forged-identity", _identity_host(), forged)

    with tempfile.TemporaryDirectory() as directory:
        dataset = Path(directory) / "sites.geojson"
        dataset.write_text('{"type": "FeatureCollection", "features": []}')
        clock = _Clock()
        file_host, authority = _file_host(clock)
        binding = file_host.bind(view_id="view-1", origin="qgis://desktop")
        ref = authority.grant_file(binding, dataset, ttl_seconds=60)
        clock.now += 61
        request = _request(
            "layers.open_vector", {"file": ref.to_wire()}, "case-expired"
        )
        reply = file_host.dispatch(binding, request)
        cases.append(
            {
                "name": "expired-handle",
                "request": request,
                "reply": reply,
                "expect": {"ok": False, "code": reply["error"]["code"]},
            }
        )

    # Releasing names kinds and ids, never a callable: a borrowed handle is
    # retained by construction and a handle the view does not hold is reported,
    # not acted on. Nothing a page sends here can turn into a delete.
    releasing = _host()
    binding = releasing.bind(view_id="view-1", origin="qgis://desktop")
    releasing.track(binding, HandleKind.BORROWED, "layer-1")
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
    coalesced.emit(subscription_id, {"percent": 10}, kind=StreamEventType.PROGRESS)
    coalesced.emit(subscription_id, {"percent": 20}, kind=StreamEventType.PROGRESS)
    coalesced.emit(subscription_id, {"row": 1})
    streams.append({"name": "progress-coalesced", "frames": coalesced.pump(binding)})

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


_SCALAR_ARRAY = re.compile(r"\[\n(?P<body>(?:[^\[\]{}\n]*\n)+?)(?P<indent>\t*)\]")
_LINE_WIDTH = 80
_TAB_WIDTH = 2


def _collapse_short_arrays(text: str) -> str:
    """Write arrays of scalars on one line when they fit, as biome would.

    ``json.dumps`` breaks every array; biome's formatter keeps an array of
    scalars on one line while it fits in 80 columns and only re-breaks the
    longer ones. Matching that here keeps the checked-in file identical whether
    the generator or the formatter wrote it last.
    """

    def collapse(match: re.Match[str]) -> str:
        items = [line.strip() for line in match.group("body").splitlines()]
        inline = "[" + " ".join(items) + "]"
        start = text.rfind("\n", 0, match.start()) + 1
        prefix = text[start : match.start()]
        width = len(prefix.expandtabs(_TAB_WIDTH)) + len(inline)
        return inline if width <= _LINE_WIDTH else match.group(0)

    return _SCALAR_ARRAY.sub(collapse, text)


def render(cases: dict[str, Any]) -> str:
    """The file's text: tabs, sorted keys and biome's short arrays."""
    return _collapse_short_arrays(json.dumps(cases, indent="\t", sort_keys=True)) + "\n"


def main() -> int:
    cases = build_cases()
    CASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Tabs and sorted keys are what biome writes for the same file, so the
    # generator and the formatter do not fight over it on every run.
    CASES_PATH.write_text(render(cases), encoding="utf-8")
    print(f"wrote {len(cases['cases'])} cases to {CASES_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
