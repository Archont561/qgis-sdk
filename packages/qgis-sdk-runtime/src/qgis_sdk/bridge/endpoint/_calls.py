"""The invocation path, and the one other call that touches the release ledger."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from qgis_sdk.bridge.endpoint._refusals import (
    ensure_not_cancelled,
    handled,
    refuse,
)
from qgis_sdk.bridge.endpoint._registry import Registry
from qgis_sdk.bridge.endpoint._types import ViewBinding
from qgis_sdk.bridge.endpoint._views import Views
from qgis_sdk.bridge.endpoint._wire import (
    checked_result,
    payload_of,
    require_input,
)
from qgis_sdk.bridge.protocol import (
    BridgeErrorCode,
    InvokeEnvelope,
    peek_call_id,
    success,
)
from qgis_sdk.bridge.resources import Handle, HandleKind, ReleaseLedger
from qgis_sdk.models.errors import QgisSdkBridgeError, QgisSdkBridgeProtocolError

_CANCELLED = "The operation was cancelled"
_RELEASE = "bridge.release"
_NOT_AUTHORIZED = "This view is not authorized to release resources"


class Calls:
    """One invocation, from envelope to reply, and the release call beside it.

    The order is the contract: parse, authorize, allowlist, cancellation,
    payload, handler, result, size. Each step either produces what the next one
    needs or refuses, and a refusal is the reply the caller gets - so the happy
    path reads as the list it is, and no step can be skipped by a different
    entry point, because these are the only entry points there are.
    """

    def __init__(
        self, *, registry: Registry, views: Views, ledger: ReleaseLedger
    ) -> None:
        self._registry = registry
        self._views = views
        self._ledger = ledger

    def invoke(
        self,
        binding: ViewBinding,
        raw: Mapping[str, Any],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Answer one invocation; a refusal inside is the reply it raises."""
        return self._invoke_reply(binding, raw, cancelled)

    def release(self, binding: ViewBinding, raw: Mapping[str, Any]) -> dict[str, Any]:
        """Release handles the view names, one outcome per handle.

        The view names kinds and ids, never a callable: releasing a borrowed
        handle is a no-op by construction, so a compromised view cannot turn one
        into a delete of the project's layer.
        """
        return self._release_reply(binding, raw)

    def track(self, binding: ViewBinding, kind: HandleKind, handle_id: str) -> Handle:
        """Record a handle the view now holds, so it can be released later."""
        handle = Handle(kind=kind, id=handle_id)
        self._ledger.track(binding.view_id, handle)
        return handle

    def _invoke_reply(
        self,
        binding: ViewBinding,
        raw: Mapping[str, Any],
        cancelled: Callable[[], bool] | None,
    ) -> dict[str, Any]:
        call_id = peek_call_id(raw) or ""
        envelope = _envelope(raw, call_id)
        self._views.require(binding, envelope.operation, envelope.call_id)
        handler = self._registry.handler_for(envelope.operation, envelope.call_id)
        ensure_not_cancelled(cancelled, envelope.call_id, _CANCELLED)
        payload = payload_of(envelope.payload, envelope.call_id)
        operation = self._registry.operation(envelope.operation)
        require_input(operation, payload, envelope.call_id)
        value = handled(handler, binding, payload, envelope.call_id)
        return success(
            envelope.call_id, checked_result(operation, value, envelope.call_id)
        )

    def _release_reply(
        self, binding: ViewBinding, raw: Mapping[str, Any]
    ) -> dict[str, Any]:
        call_id = peek_call_id(raw) or ""
        self._views.require_live(binding, call_id)
        self._views.require_authorized(
            binding, _RELEASE, call_id, reason=_NOT_AUTHORIZED
        )
        handles = _released_handles(raw, call_id)
        return success(
            call_id, {"released": self._ledger.release_all(binding.view_id, handles)}
        )


def _envelope(raw: Mapping[str, Any], call_id: str) -> InvokeEnvelope:
    """The invocation a call carries, or a refusal naming why it is malformed."""
    try:
        return InvokeEnvelope.parse(raw)
    except QgisSdkBridgeProtocolError as error:
        refuse(call_id, BridgeErrorCode.INVALID_MESSAGE, str(error))


def _released_handles(raw: Mapping[str, Any], call_id: str) -> list[Handle]:
    """The handles a release call names, parsed - or a refusal saying why not."""
    payload = raw.get("payload", {})
    if not isinstance(payload, Mapping):
        refuse(call_id, BridgeErrorCode.INVALID_PAYLOAD, "payload must be an object")
    requested = payload.get("handles", [])
    if not isinstance(requested, list):
        refuse(
            call_id,
            BridgeErrorCode.INVALID_PAYLOAD,
            "handles must be a list of handles",
        )
    try:
        return [Handle.parse(item) for item in requested]
    except QgisSdkBridgeError as error:
        refuse(call_id, BridgeErrorCode.INVALID_PAYLOAD, str(error))
