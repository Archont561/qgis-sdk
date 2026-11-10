"""How a call stops: with the reply it owes the caller, never with a return code."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, NoReturn

from qgis_sdk.bridge.endpoint._types import BoundHandler, ViewBinding
from qgis_sdk.bridge.protocol import BridgeErrorCode, failure
from qgis_sdk.models.errors import (
    QgisSdkBridgeRefusalError,
    QgisSdkError,
)


class QgisSdkRefusal(Exception):
    """A call that stops before it has a value, carrying the reply it owes.

    Every check in the endpoint has the same shape - it may refuse, and a
    refusal is a reply rather than an error - so a check raises this instead of
    returning, and a call reads one step after another. It is caught in
    ``Dispatcher.dispatch``, the one place a reply leaves the endpoint, so
    nothing here ever crosses the transport as an exception.

    It carries the SDK prefix for the same reason every other exception does:
    the workspace refuses an unprefixed exception class anywhere in the runtime,
    because one day one of them will reach user code (``test_error_names``).
    """

    def __init__(self, reply: dict[str, Any]) -> None:
        error = reply.get("error") or {}
        super().__init__(error.get("message", ""))
        self.reply = reply


def refuse(call_id: str, code: BridgeErrorCode, message: str) -> NoReturn:
    """Stop the call: ``failure(code, message)`` is the reply its caller gets."""
    raise QgisSdkRefusal(failure(call_id, code, message))


def ensure_not_cancelled(
    cancelled: Callable[[], bool] | None, call_id: str, message: str
) -> None:
    """Refuse a call whose caller has already given up on it."""
    if cancelled is not None and cancelled():
        refuse(call_id, BridgeErrorCode.CANCELLED, message)


def handled(
    handler: BoundHandler, binding: ViewBinding, payload: Any, call_id: str
) -> Any:
    """Run the handler, turning every way it can fail into the reply it owes.

    An exception crossing Qt's boundary loses the call correlation, so it never
    gets there: a ``QgisSdkError`` is forwarded (its message is written for
    users and names no host object) and anything else is replaced, because an
    unexpected exception can carry paths, handles or native repr into a view.
    """
    try:
        return handler(binding, payload)
    except QgisSdkBridgeRefusalError as error:
        refuse(call_id, BridgeErrorCode(error.code), str(error))
    except QgisSdkError as error:
        refuse(call_id, BridgeErrorCode.OPERATION_FAILED, str(error))
    except Exception:  # noqa: BLE001 - a reply must always be produced
        refuse(call_id, BridgeErrorCode.OPERATION_FAILED, _HANDLER_FAILED)


def opened(
    factory: Callable[[ViewBinding, Mapping[str, Any]], Any],
    binding: ViewBinding,
    payload: Mapping[str, Any],
    call_id: str,
) -> Any:
    """Open a stream source, refusing the same way a handler's failure is."""
    try:
        return factory(binding, payload)
    except QgisSdkBridgeRefusalError as error:
        refuse(call_id, BridgeErrorCode(error.code), str(error))
    except QgisSdkError as error:
        refuse(call_id, BridgeErrorCode.OPERATION_FAILED, str(error))
    except Exception:  # noqa: BLE001 - a reply must always be produced
        refuse(call_id, BridgeErrorCode.OPERATION_FAILED, _SOURCE_FAILED)


_HANDLER_FAILED = "The operation failed; the host recorded the details"
_SOURCE_FAILED = "The subscription failed; the host recorded the details"
