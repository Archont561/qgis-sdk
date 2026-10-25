"""One bridge host for the contract vectors, as a fixture and as BDD steps.

``tests/conftest.py`` loads this module as a pytest plugin, so the fixtures and
the step definitions below are available to every test in the suite. The
ordinary tests use :class:`ContractHost` directly; ``bridge_contract.feature``
drives the same object one sentence at a time. Neither needs QGIS: the host is
the real :class:`Dispatcher` over the SDK's fakes.

The operations and the fixed token mirror ``scripts/generate_bridge_cases.py``
on purpose - the checked-in requests have to find the same operations here.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, then, when
from qgis_sdk.bridge import BridgeOperation, Dispatcher, ViewBinding
from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.bridge.host import HostServices, register_host_operations
from qgis_sdk.bridge.resources import HandleKind
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import QgisSdkError
from qgis_sdk.testing import (
    FakeLayers,
    FakeProject,
    FakeSettings,
    FakeStyles,
    RecordingNotifications,
)

CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "qgis-sdk-bridge"
    / "tests"
    / "contracts"
    / "bridge"
    / "cases.json"
)

FIXED_TOKEN = "0123456789abcdef0123456789abcdef"

ECHO = BridgeOperation(id="demo.echo", title="Echo the payload")
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


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class ContractHost:
    """A live host the contract requests can be sent to.

    It records which operations actually ran, so a refusal can be shown to
    have happened *instead of* the work and not after it.
    """

    def __init__(self, *, allow: bool = True) -> None:
        self.ran: list[str] = []
        self.clock = _Clock()
        self.scope = ResourceScope()
        self.layers = FakeLayers(self.scope)
        self.authority = HostAuthority(clock=self.clock, token=lambda: FIXED_TOKEN)
        self.dispatcher = Dispatcher(
            description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
            authorize=(lambda binding, operation: True) if allow else None,
        )
        self._register_demo_operations()
        register_host_operations(
            self.dispatcher,
            HostServices(
                layers=self.layers,
                project=FakeProject(self.layers, self.scope),
                settings=FakeSettings(self.scope),
                styles=FakeStyles(self.layers, self.scope),
                notifications=RecordingNotifications(self.scope),
                authority=self.authority,
            ),
            only=("layers.open_vector",),
        )
        self.binding: ViewBinding = self.dispatcher.bind(
            view_id="view-1", origin="qgis://desktop"
        )
        self._cancelled = False
        self._directory: tempfile.TemporaryDirectory[str] | None = None

    def _register_demo_operations(self) -> None:
        def record(name: str, result: Any):
            def handler(payload: Any) -> Any:
                self.ran.append(name)
                if isinstance(result, Exception):
                    raise result
                return result(payload) if callable(result) else result

            return handler

        self.dispatcher.register(ECHO, record("demo.echo", lambda p: {"echo": p}))
        self.dispatcher.register(FAILS, record("demo.fails", QgisSdkError("boom")))
        self.dispatcher.register(NATIVE, record("demo.native", lambda p: object()))
        self.dispatcher.register(MALFORMED, record("demo.malformed", {"total": "many"}))

        def whoami(binding: ViewBinding, payload: Any) -> dict[str, Any]:
            self.ran.append("demo.whoami")
            return {"view_id": binding.view_id, "generation": binding.generation}

        self.dispatcher.register_bound(WHOAMI, whoami)

    # -- the set-ups a case may need, one method each -------------------------

    def fresh(self, **kwargs: Any) -> ContractHost:
        self.close()
        return ContractHost(**kwargs)

    def cancel_next_call(self) -> None:
        self._cancelled = True

    def advance_generation(self) -> None:
        self.dispatcher.advance_generation()

    def borrow(self, layer_id: str) -> None:
        self.dispatcher.track(self.binding, HandleKind.BORROWED, layer_id)

    def grant_expired_file(self, name: str = "sites.geojson") -> None:
        """Grant the view a file for a minute, then let the minute pass."""
        self._directory = tempfile.TemporaryDirectory(prefix="qgis-sdk-contract-")
        dataset = Path(self._directory.name) / name
        dataset.write_text('{"type": "FeatureCollection", "features": []}')
        self.authority.grant_file(self.binding, dataset, ttl_seconds=60)
        self.clock.now += 61

    def prepare(self, case: str) -> ContractHost:
        """Return the host a checked-in case assumes, set up by its name."""
        if case == "not-authorized":
            return self.fresh(allow=False)
        if case == "cancelled":
            self.cancel_next_call()
        elif case == "stale-generation":
            self.advance_generation()
        elif case == "release-borrowed":
            self.borrow("layer-1")
        elif case == "expired-handle":
            self.grant_expired_file()
        return self

    # -- the exchange -----------------------------------------------------------

    def send(self, request: dict[str, Any]) -> dict[str, Any]:
        cancelled = self._cancelled
        self._cancelled = False
        return self.dispatcher.dispatch(
            self.binding, request, cancelled=lambda: cancelled
        )

    @staticmethod
    def expectation(reply: dict[str, Any]) -> dict[str, Any]:
        """Reduce a reply to the shape the cases file records as ``expect``."""
        if reply["ok"]:
            return {"ok": True, "value": reply["value"]}
        return {"ok": False, "code": reply["error"]["code"]}

    def close(self) -> None:
        self.scope.close()
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None


# -- fixtures ----------------------------------------------------------------


@pytest.fixture(scope="session")
def bridge_cases() -> dict[str, dict[str, Any]]:
    """The checked-in contract vectors, by name."""
    document = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return {case["name"]: case for case in document["cases"]}


@pytest.fixture
def contract_host():
    host = ContractHost()
    yield host
    host.close()


# -- steps -------------------------------------------------------------------


@given("a host with a bound view", target_fixture="host")
def host_with_bound_view(contract_host: ContractHost) -> ContractHost:
    return contract_host


@given("a host that authorizes nothing", target_fixture="host")
def host_that_authorizes_nothing(contract_host: ContractHost) -> ContractHost:
    return contract_host.fresh(allow=False)


@given("the call is cancelled before the operation runs")
def call_is_cancelled(host: ContractHost) -> None:
    host.cancel_next_call()


@given("the view holds a file grant that has since expired")
def file_grant_expired(host: ContractHost) -> None:
    host.grant_expired_file()


@given(parsers.parse('the view borrowed the layer "{layer_id}"'))
def view_borrowed(host: ContractHost, layer_id: str) -> None:
    host.borrow(layer_id)


@when(parsers.parse('the page sends the "{case}" request'), target_fixture="exchange")
def page_sends_case(
    host: ContractHost, bridge_cases: dict[str, dict[str, Any]], case: str
) -> dict[str, Any]:
    request = bridge_cases[case]["request"]
    return {"case": case, "request": request, "reply": host.send(request)}


@then(parsers.parse('the reply is the one checked in for "{case}"'))
def reply_matches_checked_in(
    exchange: dict[str, Any], bridge_cases: dict[str, dict[str, Any]], case: str
) -> None:
    assert exchange["case"] == case
    assert ContractHost.expectation(exchange["reply"]) == bridge_cases[case]["expect"]


@then(parsers.parse('the reply names view "{view_id}" at generation {generation:d}'))
def reply_names_view(exchange: dict[str, Any], view_id: str, generation: int) -> None:
    assert exchange["reply"]["value"] == {
        "view_id": view_id,
        "generation": generation,
    }


@then("the operation did not run")
def operation_did_not_run(host: ContractHost, exchange: dict[str, Any]) -> None:
    assert exchange["request"]["operation"] not in host.ran


@then("the reply carries no value")
def reply_carries_no_value(exchange: dict[str, Any]) -> None:
    assert "value" not in exchange["reply"]
    assert "many" not in json.dumps(exchange["reply"])


@then("no layer was opened")
def no_layer_was_opened(host: ContractHost) -> None:
    assert host.layers.list_layers() == ()


@then(parsers.parse('the view no longer holds "{layer_id}"'))
def view_no_longer_holds(host: ContractHost, layer_id: str) -> None:
    """Retained by the host, forgotten by the view: a second release of the
    same handle finds nothing to do."""
    outcomes = {
        item["id"]: item["outcome"]
        for item in host.send(
            {
                "protocol": 1,
                "kind": "release",
                "call_id": "again",
                "payload": {"handles": [{"kind": "borrowed", "id": layer_id}]},
            }
        )["value"]["released"]
    }
    assert outcomes == {layer_id: "already_released"}
