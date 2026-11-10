"""What crosses the wire, and the checks a value has to pass first."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from qgis_sdk.bridge.endpoint._refusals import refuse
from qgis_sdk.bridge.protocol import (
    MAX_INLINE_BYTES,
    BridgeErrorCode,
    BridgeOperation,
    to_wire,
)
from qgis_sdk.bridge.schema import validate
from qgis_sdk.declarations import WIRE_VALUE_METHOD
from qgis_sdk.models.errors import QgisSdkBridgeError


def payload_of(payload: Any, call_id: str) -> Any:
    """The payload as it will cross the wire, or a refusal naming why it cannot."""
    try:
        return to_wire(payload)
    except QgisSdkBridgeError as error:
        refuse(call_id, BridgeErrorCode.INVALID_PAYLOAD, str(error))


def require_input(operation: BridgeOperation, payload: Any, call_id: str) -> None:
    """Refuse a payload that does not match the operation's declared request."""
    refusal = input_refusal(operation, payload)
    if refusal is not None:
        refuse(call_id, BridgeErrorCode.INVALID_PAYLOAD, refusal)


def checked_result(operation: BridgeOperation, value: Any, call_id: str) -> Any:
    """The result as it will cross the wire, once it is JSON-safe and within size."""
    wire_value = wire_value_of(value, call_id)
    refusal = output_refusal(operation, wire_value)
    if refusal is not None:
        refuse(call_id, BridgeErrorCode.INVALID_RESULT, refusal)
    require_inline(wire_value, call_id)
    return wire_value


def wire_value_of(value: Any, call_id: str) -> Any:
    """The handler's value as it will cross the wire, or a refusal when it cannot."""
    try:
        return to_wire(value)
    except QgisSdkBridgeError as error:
        refuse(call_id, BridgeErrorCode.NOT_SERIALIZABLE, str(error))


def require_inline(wire_value: Any, call_id: str) -> None:
    """Refuse a result above the inline ceiling; the page should fetch a blob."""
    size = wire_size(wire_value)
    if size > MAX_INLINE_BYTES:
        refuse(
            call_id,
            BridgeErrorCode.INVALID_RESULT,
            f"The result is {size} bytes, above the {MAX_INLINE_BYTES}-byte "
            "inline ceiling; return a BlobRef and let the page fetch chunks "
            "(decision-59)",
        )


def wire_result(value: Any) -> Any:
    """Turn declared value objects into plain JSON before the boundary check.

    A declared action returns the dataclass its annotation names, and the
    declaration already described that dataclass as an object schema. Converting
    here keeps :func:`~qgis_sdk.bridge.protocol.to_wire` strict for everything
    else: a Qt or QGIS object is still refused, because only dataclasses, lists
    and mappings are unwrapped.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    wire = getattr(type(value), WIRE_VALUE_METHOD, None)
    if wire is not None:
        return wire_result(wire(value))
    if isinstance(value, (list, tuple)):
        return [wire_result(item) for item in value]
    if isinstance(value, Mapping):
        return {key: wire_result(item) for key, item in value.items()}
    return value


def wire_size(value: Any) -> int:
    """Measure a reply the way the transport will, in bytes of JSON text.

    The ceiling is about what crosses QWebChannel, so it is measured after the
    value is already known to be JSON-safe: no encoder fallback, no surprises.
    """
    try:
        return len(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        )
    except (TypeError, ValueError):
        return 0


def input_refusal(operation: BridgeOperation, payload: Any) -> str | None:
    """Return why ``payload`` is not a valid request, or ``None`` when it is."""
    if operation.request is None:
        return None
    try:
        validate(payload, operation.request, path="payload")
    except QgisSdkBridgeError as error:
        return str(error)
    return None


def output_refusal(operation: BridgeOperation, value: Any) -> str | None:
    """Return why ``value`` is not a valid result, or ``None`` when it is."""
    if operation.result is None:
        return None
    try:
        validate(value, operation.result, path="result", allow_unknown=True)
    except QgisSdkBridgeError as error:
        return str(error)
    return None
