"""Blobs above the inline ceiling, and the acknowledgements that bound a stream.

decision-59 splits one promise in two. A result larger than the inline cap is
not sent: the host keeps the bytes, hands the page a :class:`BlobRef` and serves
bounded chunks that the page verifies against the checksum in the ref. A pushed
stream is not left to run ahead of its consumer: the page acknowledges each
frame it delivered, and the host stops after a bounded number of unacknowledged
frames.

None of this needs Qt, a browser or a running QGIS. What it needs is the
dispatcher and the authority, so that is what the tests drive - the native
measurement of the cap itself lives in the QGIS-gated suite and is not claimed
here.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

import pytest
from qgis_sdk.bridge import BridgeErrorCode, BridgeOperation, Dispatcher, ViewBinding
from qgis_sdk.bridge.authority import (
    BLOB_TTL_SECONDS,
    MAX_BLOB_BYTES,
    MAX_BLOBS_PER_VIEW,
    HostAuthority,
)
from qgis_sdk.bridge.host import MAX_PAGE, HostServices
from qgis_sdk.bridge.protocol import BRIDGE_PROTOCOL_VERSION, MAX_INLINE_BYTES
from qgis_sdk.bridge.streams import (
    MAX_IN_FLIGHT_FRAMES,
    MAX_QUEUED_EVENTS,
    StreamEventType,
)
from qgis_sdk.models.blobs import BLOB_REF_KIND, BlobRef
from qgis_sdk.models.errors import (
    QgisSdkBridgeError,
    QgisSdkStaleHandleError,
    QgisSdkUnknownHandleError,
)

ORIGIN = "qgis://desktop"
PUSH = BridgeOperation(id="demo.push", title="A stream the host pushes into")


class _Layers:
    def list_layers(self) -> tuple[Any, ...]:
        return ()

    def layer(self, layer_id: str) -> Any:  # pragma: no cover - not called here
        raise AssertionError(layer_id)


class _Project:
    def layer_ids(self) -> tuple[str, ...]:
        return ()


class _Settings:
    def get(self, key: str, default: str | None = None) -> str | None:
        return default


class _Styles:
    def apply_style(self, layer_id: str, style: str) -> None:  # pragma: no cover
        raise AssertionError((layer_id, style))


class _Notifications:
    def info(self, message: str) -> None:  # pragma: no cover - not called here
        raise AssertionError(message)


def _services() -> HostServices:
    """The four curated services the host surface needs, with nothing behind them."""
    return HostServices(
        layers=_Layers(),
        project=_Project(),
        settings=_Settings(),
        styles=_Styles(),
        notifications=_Notifications(),
        authority=HostAuthority(),
    )


def _dispatcher(services: HostServices) -> Dispatcher:
    from qgis_sdk.bridge.host import register_host_operations

    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    dispatcher.register_stream(PUSH, lambda payload: None)
    register_host_operations(dispatcher, services)
    return dispatcher


def _binding(dispatcher: Dispatcher, view_id: str = "view-1") -> ViewBinding:
    return dispatcher.bind(view_id=view_id, origin=ORIGIN)


def _get(dispatcher: Dispatcher, binding: ViewBinding, payload: Any) -> dict[str, Any]:
    return dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "invoke",
            "call_id": "blob-1",
            "operation": "blob.get",
            "payload": payload,
        },
    )


def _ack(
    dispatcher: Dispatcher, binding: ViewBinding, subscription_id: str, seq: int
) -> dict[str, Any]:
    return dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "ack",
            "call_id": f"ack-{seq}",
            "subscription_id": subscription_id,
            "seq": seq,
        },
    )


def _subscribe(dispatcher: Dispatcher, binding: ViewBinding) -> str:
    reply = dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "subscribe",
            "call_id": "sub-1",
            "operation": PUSH.id,
            "payload": {},
        },
    )
    return reply["value"]["subscription_id"]


def _fetch(
    dispatcher: Dispatcher, binding: ViewBinding, ref: BlobRef, *, chunk: int = 4096
) -> bytes:
    """Read a whole blob the way the page does: follow ``next_offset``."""
    pieces: list[bytes] = []
    offset: int | None = 0
    while offset is not None:
        reply = _get(
            dispatcher,
            binding,
            {"blob": ref.to_wire(), "offset": offset, "length": chunk},
        )
        assert reply["ok"] is True, reply
        value = reply["value"]
        pieces.append(base64.b64decode(value["data_base64"]))
        offset = value["next_offset"]
    return b"".join(pieces)


# -- the ref a large result comes back as (AC #1) ---------------------------


def test_a_payload_above_the_cap_becomes_a_ref_and_reads_back_byte_for_byte() -> None:
    authority = HostAuthority()
    binding = ViewBinding(view_id="view-1", generation=0, origin=ORIGIN)
    payload = bytes(range(256)) * 4096

    envelope = authority.inline_or_blob(binding, payload, media_type="image/png")

    assert "inline_base64" not in envelope
    ref = BlobRef.from_wire(envelope["blob"])
    assert envelope["size"] == len(payload)
    assert ref.size == len(payload)
    assert ref.checksum == hashlib.sha256(payload).hexdigest()
    assert ref.media_type == "image/png"
    assert ref.kind == BLOB_REF_KIND


def test_the_fetch_loop_returns_the_payload_and_the_matching_checksum() -> None:
    services = _services()
    dispatcher = _dispatcher(services)
    binding = _binding(dispatcher)
    payload = b"".join(bytes([index % 251]) for index in range(300_000))

    envelope = services.authority.inline_or_blob(binding, payload)
    ref = BlobRef.from_wire(envelope["blob"])

    assembled = _fetch(dispatcher, binding, ref, chunk=64 * 1024)

    assert assembled == payload
    assert hashlib.sha256(assembled).hexdigest() == ref.checksum


def test_a_small_payload_stays_inline_and_mints_nothing() -> None:
    authority = HostAuthority()
    binding = ViewBinding(view_id="view-1", generation=0, origin=ORIGIN)

    envelope = authority.inline_or_blob(binding, b"small", cap=1024)

    assert base64.b64decode(envelope["inline_base64"]) == b"small"
    assert envelope["size"] == 5
    assert "blob" not in envelope


def test_the_last_chunk_says_so_by_leaving_next_offset_null() -> None:
    services = _services()
    dispatcher = _dispatcher(services)
    binding = _binding(dispatcher)
    ref = services.authority.mint_blob(binding, b"0123456789")

    first = _get(dispatcher, binding, {"blob": ref.to_wire(), "offset": 0, "length": 4})
    second = _get(
        dispatcher, binding, {"blob": ref.to_wire(), "offset": 8, "length": 4}
    )

    assert first["value"]["next_offset"] == 4
    assert second["value"]["next_offset"] is None
    assert second["value"]["length"] == 2
    assert base64.b64decode(second["value"]["data_base64"]) == b"89"
    assert second["value"]["checksum"] == ref.checksum


def test_a_chunk_request_beyond_the_chunk_ceiling_is_refused_by_name() -> None:
    services = _services()
    dispatcher = _dispatcher(services)
    binding = _binding(dispatcher)
    ref = services.authority.mint_blob(binding, b"x" * 512)

    refused = _get(dispatcher, binding, {"blob": ref.to_wire(), "length": 10**7})

    assert refused["ok"] is False
    assert refused["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value
    assert "length" in refused["error"]["message"]


def test_an_over_size_page_request_is_refused_by_name() -> None:
    services = _services()
    dispatcher = _dispatcher(services)
    binding = _binding(dispatcher)

    refused = dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": "page-1",
            "operation": "layers.list",
            "payload": {"limit": MAX_PAGE + 1},
        },
    )

    assert refused["ok"] is False
    assert refused["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value
    assert "limit" in refused["error"]["message"]


def test_a_blob_dies_with_its_view() -> None:
    services = _services()
    dispatcher = _dispatcher(services)
    binding = _binding(dispatcher)
    ref = services.authority.mint_blob(binding, b"payload")

    services.authority.release_view(binding)

    gone = _get(dispatcher, binding, {"blob": ref.to_wire()})
    assert gone["ok"] is False
    assert gone["error"]["code"] == BridgeErrorCode.UNKNOWN_HANDLE.value


def test_a_blob_from_a_replaced_generation_is_stale() -> None:
    services = _services()
    dispatcher = _dispatcher(services)
    binding = _binding(dispatcher)
    ref = services.authority.mint_blob(binding, b"payload")

    dispatcher.advance_generation()
    later = _binding(dispatcher)

    refused = _get(dispatcher, later, {"blob": ref.to_wire()})
    assert refused["error"]["code"] == BridgeErrorCode.STALE_HANDLE.value


def test_another_view_cannot_read_a_blob_it_was_never_given() -> None:
    services = _services()
    dispatcher = _dispatcher(services)
    owner = _binding(dispatcher, "view-1")
    other = _binding(dispatcher, "view-2")
    ref = services.authority.mint_blob(owner, b"payload")

    refused = _get(dispatcher, other, {"blob": ref.to_wire()})

    assert refused["error"]["code"] == BridgeErrorCode.UNKNOWN_HANDLE.value
    assert "not one this view holds" in refused["error"]["message"]


def test_the_authority_refuses_a_payload_it_would_have_to_keep_whole() -> None:
    authority = HostAuthority()
    binding = ViewBinding(view_id="view-1", generation=0, origin=ORIGIN)

    with pytest.raises(QgisSdkBridgeError, match="is a file"):
        authority.mint_blob(binding, b"x" * (MAX_BLOB_BYTES + 1))


def test_a_view_may_hold_only_so_many_blobs() -> None:
    authority = HostAuthority()
    binding = ViewBinding(view_id="view-1", generation=0, origin=ORIGIN)
    for _ in range(MAX_BLOBS_PER_VIEW):
        authority.mint_blob(binding, b"x", ttl_seconds=None)

    with pytest.raises(QgisSdkBridgeError, match="released with the view"):
        authority.mint_blob(binding, b"x")


def test_an_expired_blob_is_stale_rather_than_unknown() -> None:
    now = [0.0]
    authority = HostAuthority(clock=lambda: now[0])
    binding = ViewBinding(view_id="view-1", generation=0, origin=ORIGIN)
    ref = authority.mint_blob(binding, b"payload", ttl_seconds=10)

    now[0] = 11.0

    with pytest.raises(QgisSdkStaleHandleError, match="expired"):
        authority.read_blob(binding, ref.to_wire())


def test_a_ref_that_is_not_a_ref_is_unknown_rather_than_a_crash() -> None:
    authority = HostAuthority()
    binding = ViewBinding(view_id="view-1", generation=0, origin=ORIGIN)

    for raw in ({}, {"kind": "file", "id": "a" * 32}, {"kind": "blob", "id": ""}):
        with pytest.raises(QgisSdkUnknownHandleError):
            authority.read_blob(binding, raw)


def test_the_ref_carries_the_moment_it_stops_being_readable() -> None:
    authority = HostAuthority()
    binding = ViewBinding(view_id="view-1", generation=0, origin=ORIGIN)

    ref = authority.mint_blob(binding, b"payload")

    assert ref.expires_at is not None
    assert ref.to_wire()["expires_at"] == ref.expires_at
    assert BLOB_TTL_SECONDS > 0


def test_a_reply_above_the_inline_ceiling_is_refused_and_names_the_cure() -> None:
    oversized = BridgeOperation(id="demo.big", title="Return too much")
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    dispatcher.register(oversized, lambda payload: {"text": "x" * MAX_INLINE_BYTES})
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    refused = dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": "big-1",
            "operation": oversized.id,
            "payload": {},
        },
    )

    assert refused["ok"] is False
    assert refused["error"]["code"] == BridgeErrorCode.INVALID_RESULT.value
    assert "BlobRef" in refused["error"]["message"]


# -- acknowledgements bound what is in flight (AC #2) -----------------------


def test_a_pushed_stream_stops_after_the_in_flight_bound_until_it_is_acked() -> None:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    dispatcher.register_stream(PUSH, lambda payload: None)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding)
    for index in range(MAX_IN_FLIGHT_FRAMES + 4):
        assert dispatcher.emit(subscription_id, {"index": index}) is True

    first = dispatcher.pump(binding, limit=64)

    assert [frame["seq"] for frame in first] == list(range(MAX_IN_FLIGHT_FRAMES))
    assert dispatcher.pump(binding, limit=64) == []

    assert _ack(dispatcher, binding, subscription_id, MAX_IN_FLIGHT_FRAMES - 1)["ok"]
    later = dispatcher.pump(binding, limit=64)

    assert [frame["seq"] for frame in later] == list(range(MAX_IN_FLIGHT_FRAMES, 12))


def test_progress_is_coalesced_until_the_client_reads_it() -> None:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    dispatcher.register_stream(PUSH, lambda payload: None)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding)
    for percent in (10, 20, 30):
        dispatcher.emit(
            subscription_id, {"percent": percent}, kind=StreamEventType.PROGRESS
        )

    frames = dispatcher.pump(binding)

    assert len(frames) == 1
    assert frames[0]["event"]["payload"] == {"percent": 30}


def test_an_ack_names_the_watermark_and_how_much_is_in_flight() -> None:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    dispatcher.register_stream(PUSH, lambda payload: None)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding)
    dispatcher.emit(subscription_id, {"index": 0})
    dispatcher.emit(subscription_id, {"index": 1})
    dispatcher.pump(binding)

    reply = _ack(dispatcher, binding, subscription_id, 0)

    assert reply["ok"] is True
    assert reply["value"] == {
        "subscription_id": subscription_id,
        "acknowledged": 1,
        "in_flight": 1,
    }


def test_a_repeated_ack_is_a_no_op_and_an_impossible_one_is_refused() -> None:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    dispatcher.register_stream(PUSH, lambda payload: None)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding)
    dispatcher.emit(subscription_id, {"index": 0})
    dispatcher.pump(binding)

    assert _ack(dispatcher, binding, subscription_id, 0)["ok"] is True
    repeat = _ack(dispatcher, binding, subscription_id, 0)
    impossible = _ack(dispatcher, binding, subscription_id, 9)

    assert repeat["ok"] is True
    assert repeat["value"]["acknowledged"] == 1
    assert impossible["ok"] is False
    assert impossible["error"]["code"] == BridgeErrorCode.INVALID_MESSAGE.value
    assert "never handed to this view" in impossible["error"]["message"]


def test_an_ack_for_another_views_stream_is_refused() -> None:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    dispatcher.register_stream(PUSH, lambda payload: None)
    owner = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    other = dispatcher.bind(view_id="view-2", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, owner)
    dispatcher.emit(subscription_id, {"index": 0})
    dispatcher.pump(owner)

    refused = _ack(dispatcher, other, subscription_id, 0)

    assert refused["ok"] is False
    assert refused["error"]["code"] == BridgeErrorCode.NOT_AUTHORIZED.value


def test_an_ack_after_the_stream_ended_still_advances_nothing_but_is_accepted() -> None:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    dispatcher.register_stream(PUSH, lambda payload: None)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding)
    dispatcher.emit(subscription_id, {"index": 0})
    dispatcher.pump(binding)
    dispatcher.dispose(binding)

    late = _ack(dispatcher, binding, subscription_id, 0)

    assert late["ok"] is True
    assert late["value"]["acknowledged"] is None
    assert late["value"]["in_flight"] == 0


def test_an_ack_for_a_generation_that_was_replaced_is_stale() -> None:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    dispatcher.register_stream(PUSH, lambda payload: None)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding)
    dispatcher.advance_generation()

    refused = _ack(dispatcher, binding, subscription_id, 0)

    assert refused["ok"] is False
    assert refused["error"]["code"] == BridgeErrorCode.STALE_GENERATION.value


def test_a_well_formed_ack_is_required_before_the_lookup() -> None:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    for payload in (
        {"call_id": "a", "kind": "ack"},
        {"call_id": "a", "kind": "ack", "subscription_id": "s", "seq": -1},
        {"call_id": "a", "kind": "ack", "subscription_id": "", "seq": 0},
        {"call_id": "a", "kind": "ack", "subscription_id": "s", "seq": "0"},
    ):
        refused = dispatcher.dispatch(
            binding, {"protocol": BRIDGE_PROTOCOL_VERSION, **payload}
        )
        assert refused["ok"] is False, payload
        assert refused["error"]["code"] == BridgeErrorCode.INVALID_MESSAGE.value


def test_the_queue_overflow_gap_still_ends_a_stream_that_is_never_read() -> None:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    dispatcher.register_stream(PUSH, lambda payload: None)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding)
    for index in range(MAX_QUEUED_EVENTS + 1):
        dispatcher.emit(subscription_id, {"index": index})

    frames: list[dict[str, Any]] = []
    for _ in range(MAX_QUEUED_EVENTS):
        batch = dispatcher.pump(binding, limit=MAX_QUEUED_EVENTS + 1)
        if not batch:
            break
        frames.extend(batch)
        for frame in batch:
            if "terminal" not in frame:
                _ack(dispatcher, binding, subscription_id, frame["seq"])
        if any("terminal" in frame for frame in batch):
            break

    assert frames[-1]["terminal"]["kind"] == "gap"
    assert frames[-1]["terminal"]["dropped"] == 1
    assert [frame["seq"] for frame in frames[:-1]] == list(range(MAX_QUEUED_EVENTS))
