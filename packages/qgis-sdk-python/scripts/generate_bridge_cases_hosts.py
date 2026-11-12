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

from pathlib import Path
from typing import Any

from qgis_sdk.bridge import (
    BRIDGE_PROTOCOL_VERSION,
    BridgeOperation,
    Dispatcher,
    ViewBinding,
)
from qgis_sdk.bridge.authority import FilePolicy, HostAuthority
from qgis_sdk.bridge.host import HostServices, register_host_operations
from qgis_sdk.bridge.resources import HandleKind
from qgis_sdk.bridge.streams import (
    MAX_FRAMES_PER_PUMP,
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


FIXED_TOKEN = "0123456789abcdef0123456789abcdef"


def request(operation: str, payload: Any = None, call_id: str = "case") -> dict:
    return {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "call_id": call_id,
        "operation": operation,
        "payload": {} if payload is None else payload,
    }


def stream_host() -> Dispatcher:
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


def subscribe(dispatcher: Dispatcher, binding, operation: str) -> str:
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


def identity_host() -> Dispatcher:
    dispatcher = _host()
    dispatcher.register_bound(WHOAMI, _whoami)
    return dispatcher


class _Clock:
    """A clock the case advances by hand, so an expiry is a fact and not a sleep."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def file_host(clock: _Clock) -> tuple[Dispatcher, HostAuthority]:
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


def deep(root: int) -> list:
    payload: list = []
    current = payload
    for _ in range(root):
        nested: list = []
        current.append(nested)
        current = nested
    return payload


def record(
    cases: list[dict[str, Any]],
    name: str,
    dispatcher: Dispatcher,
    request: dict,
    *,
    advance: bool = False,
) -> None:
    """Run one request through a real dispatcher and keep the whole exchange."""
    binding = dispatcher.bind(view_id="view-1", origin="qgis://desktop")
    if advance:
        dispatcher.advance_generation()
    reply = dispatcher.dispatch(binding, request)
    expect: dict[str, Any] = {"ok": reply["ok"]}
    if reply["ok"]:
        expect["value"] = reply["value"]
    else:
        expect["code"] = reply["error"]["code"]
    cases.append({"name": name, "request": request, "reply": reply, "expect": expect})


__all__ = [
    "MAX_FRAMES_PER_PUMP",
    "MAX_QUEUED_EVENTS",
    "FilePolicy",
    "HandleKind",
    "StreamEventType",
]
