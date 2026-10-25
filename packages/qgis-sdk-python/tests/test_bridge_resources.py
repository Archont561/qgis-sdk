"""What releasing a handle means, per kind, and what it must never do.

AC #7 asks for three distinctions that are easy to state and easy to lose in an
implementation: a borrowed layer is not a temporary output, a subscription is
neither, and closing something twice is normal rather than an error. The tests
below pin all three down, first on the ledger alone and then through the
dispatcher a real view would use.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from qgis_sdk.bridge import BridgeOperation, Dispatcher
from qgis_sdk.bridge.resources import Handle, HandleKind, ReleaseLedger, ReleaseOutcome
from qgis_sdk.models.errors import QgisSdkBridgeError

ORIGIN = "qgis://desktop"
TICKS = BridgeOperation(id="demo.ticks", title="Emit a tick")
RELEASE = "bridge.release"


def _ledger(deleted: list[str], disposed: list[str]) -> ReleaseLedger:
    def dispose(subscription_id: str) -> bool:
        if subscription_id in disposed:
            return False
        disposed.append(subscription_id)
        return True

    return ReleaseLedger(delete_owned=deleted.append, dispose_subscription=dispose)


def _host(*, allow: bool = True, ledger: ReleaseLedger | None = None) -> Dispatcher:
    dispatcher = Dispatcher(
        authorize=(lambda binding, operation: True) if allow else None,
        ledger=ledger,
    )
    dispatcher.register_stream(TICKS, lambda payload: _ticks())
    return dispatcher


def _ticks() -> Iterator[dict[str, Any]]:
    for index in range(100):
        yield {"index": index}


def _release(dispatcher: Dispatcher, binding, handles: list[dict[str, str]]):
    return dispatcher.dispatch(
        binding,
        {
            "protocol": 1,
            "kind": "release",
            "call_id": "release-1",
            "payload": {"handles": handles},
        },
    )


def test_releasing_a_borrowed_handle_never_deletes_the_project_layer() -> None:
    deleted: list[str] = []
    ledger = _ledger(deleted, [])
    project = {"sites": object()}
    ledger.track("view-1", Handle(kind=HandleKind.BORROWED, id="sites"))

    outcome = ledger.release("view-1", Handle(kind=HandleKind.BORROWED, id="sites"))

    assert outcome is ReleaseOutcome.BORROWED_RETAINED
    assert deleted == []
    assert list(project) == ["sites"]


def test_releasing_an_owned_output_deletes_it_exactly_once() -> None:
    deleted: list[str] = []
    ledger = _ledger(deleted, [])
    handle = Handle(kind=HandleKind.OWNED, id="tmp-buffer-7")
    ledger.track("view-1", handle)

    first = ledger.release("view-1", handle)
    second = ledger.release("view-1", handle)

    assert first is ReleaseOutcome.DELETED
    assert second is ReleaseOutcome.ALREADY_RELEASED
    assert deleted == ["tmp-buffer-7"]


def test_releasing_a_subscription_that_already_ended_is_not_an_error() -> None:
    disposed: list[str] = []
    ledger = _ledger([], disposed)
    handle = Handle(kind=HandleKind.SUBSCRIPTION, id="s1")
    ledger.track("view-1", handle)
    ledger.track("view-1", Handle(kind=HandleKind.SUBSCRIPTION, id="s2"))

    assert ledger.release("view-1", handle) is ReleaseOutcome.SUBSCRIPTION_DISPOSED
    assert ledger.release("view-1", handle) is ReleaseOutcome.ALREADY_RELEASED
    # s2 ended on its own first, so the host's disposal reports that there was
    # nothing left to dispose; the view is told the truth rather than an error.
    assert ledger.dispose_subscription("s2") is True
    assert (
        ledger.release("view-1", Handle(kind=HandleKind.SUBSCRIPTION, id="s2"))
        is ReleaseOutcome.ALREADY_RELEASED
    )
    assert disposed == ["s1", "s2"]


def test_a_handle_the_view_does_not_hold_is_not_released_again() -> None:
    deleted: list[str] = []
    ledger = _ledger(deleted, [])

    outcome = ledger.release("view-1", Handle(kind=HandleKind.OWNED, id="tmp-1"))

    assert outcome is ReleaseOutcome.ALREADY_RELEASED
    assert deleted == []


def test_a_handle_carries_a_kind_and_an_id_and_nothing_else() -> None:
    assert Handle.parse({"kind": "owned", "id": "tmp-1"}) == Handle(
        kind=HandleKind.OWNED, id="tmp-1"
    )

    for raw in (
        {"kind": "owned"},
        {"kind": "nope", "id": "tmp-1"},
        {"kind": "owned", "id": "  "},
        {"kind": "owned", "id": "tmp-1", "callable": "delete_everything"},
        "owned:tmp-1",
    ):
        with pytest.raises(QgisSdkBridgeError):
            Handle.parse(raw)


def test_release_view_reports_every_outcome_for_a_view_that_is_leaving() -> None:
    deleted: list[str] = []
    ledger = _ledger(deleted, [])
    ledger.track("view-1", Handle(kind=HandleKind.BORROWED, id="sites"))
    ledger.track("view-1", Handle(kind=HandleKind.OWNED, id="tmp-1"))

    outcomes = ledger.release_view("view-1")

    assert outcomes == [
        {"kind": "borrowed", "id": "sites", "outcome": "borrowed_retained"},
        {"kind": "owned", "id": "tmp-1", "outcome": "deleted"},
    ]
    assert ledger.handles("view-1") == ()


def test_the_dispatcher_tracks_the_subscriptions_a_view_opens() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    reply = dispatcher.dispatch(
        binding,
        {
            "protocol": 1,
            "kind": "subscribe",
            "call_id": "sub-1",
            "operation": TICKS.id,
            "payload": {},
        },
    )
    subscription_id = reply["value"]["subscription_id"]

    assert dispatcher.track(binding, HandleKind.BORROWED, "sites") == Handle(
        kind=HandleKind.BORROWED, id="sites"
    )
    released = _release(
        dispatcher,
        binding,
        [{"kind": "subscription", "id": subscription_id}],
    )

    assert released["value"]["released"] == [
        {
            "kind": "subscription",
            "id": subscription_id,
            "outcome": "subscription_disposed",
        }
    ]
    assert dispatcher.subscriptions() == ()
    assert dispatcher.pump(binding) == []


def test_a_view_cannot_release_what_another_view_holds() -> None:
    deleted: list[str] = []
    dispatcher = _host(ledger=_ledger(deleted, []))
    owner = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    stranger = dispatcher.bind(view_id="view-2", origin=ORIGIN)
    dispatcher.track(owner, HandleKind.OWNED, "tmp-1")

    reply = _release(dispatcher, stranger, [{"kind": "owned", "id": "tmp-1"}])

    assert reply["value"]["released"] == [
        {"kind": "owned", "id": "tmp-1", "outcome": "already_released"}
    ]
    assert deleted == []


def test_release_is_authorized_like_every_other_call() -> None:
    dispatcher = _host(allow=False)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = _release(dispatcher, binding, [{"kind": "borrowed", "id": "sites"}])

    assert reply["error"]["code"] == "not_authorized"


def test_a_malformed_handle_list_is_refused_before_anything_is_released() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    dispatcher.track(binding, HandleKind.OWNED, "tmp-1")

    bad_kind = _release(dispatcher, binding, [{"kind": "database", "id": "tmp-1"}])
    not_a_list = dispatcher.dispatch(
        binding,
        {
            "protocol": 1,
            "kind": "release",
            "call_id": "release-2",
            "payload": {"handles": "tmp-1"},
        },
    )

    assert bad_kind["error"]["code"] == "invalid_payload"
    assert not_a_list["error"]["code"] == "invalid_payload"
    assert dispatcher.track(binding, HandleKind.OWNED, "tmp-1") == Handle(
        kind=HandleKind.OWNED, id="tmp-1"
    )


def test_a_stale_generation_releases_nothing() -> None:
    deleted: list[str] = []
    dispatcher = _host(ledger=_ledger(deleted, []))
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    dispatcher.track(binding, HandleKind.OWNED, "tmp-1")
    dispatcher.advance_generation()

    reply = _release(dispatcher, binding, [{"kind": "owned", "id": "tmp-1"}])

    assert reply["error"]["code"] == "stale_generation"
    assert deleted == []
