"""The registration: turn the declared operations into the dispatcher's surface."""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from typing import TYPE_CHECKING

from qgis_sdk.bridge.host._context import HostHandler, _Host
from qgis_sdk.bridge.host._operations import HOST_OPERATIONS, HostOperation
from qgis_sdk.bridge.host._sources import EditingSessions
from qgis_sdk.bridge.host.handlers import HANDLERS
from qgis_sdk.bridge.protocol import BridgeOperation
from qgis_sdk.models.errors import QgisSdkBridgeError

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import Dispatcher
    from qgis_sdk.bridge.host._services import HostServices


def register_host_operations(
    dispatcher: Dispatcher,
    services: HostServices,
    *,
    only: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Register the curated operations on ``dispatcher`` and return their ids.

    ``only`` narrows the surface to a subset, which is how an application with a
    grant model hides what a view may not use instead of refusing it later. The
    ids that were registered are also the ids the handshake advertises, because
    the handshake reads the allowlist.

    Both failures happen before anything is registered. ``only`` is an
    authority-bearing argument, so an id it names that this module does not
    declare is a typo that would otherwise narrow the surface in silence; and a
    conflict with what the dispatcher already carries would otherwise leave the
    operations registered before it in place, on a call whose caller was told it
    failed.
    """
    editing = EditingSessions()
    host = _Host(services=services, editing=editing)
    wanted = _selected(only)
    operations = _operations(wanted)
    _refuse_taken(dispatcher, operations)
    dispatcher.register_editing(close=editing.close, close_view=editing.close_view)
    _register(dispatcher, wanted, operations, host)
    return tuple(operation.id for operation in operations)


def _operations(wanted: Sequence[HostOperation]) -> list[BridgeOperation]:
    """Return the protocol operations the declared ones describe, description left behind."""
    return [
        BridgeOperation(
            id=operation.id,
            title=operation.title,
            request=operation.request,
            result=operation.result,
            events=operation.events,
        )
        for operation in wanted
    ]


def _refuse_taken(
    dispatcher: Dispatcher, operations: Sequence[BridgeOperation]
) -> None:
    """Refuse the whole registration when an id is already allowlisted."""
    taken = {operation.id for operation in dispatcher.operations()}
    conflicts = [operation.id for operation in operations if operation.id in taken]
    if conflicts:
        raise QgisSdkBridgeError(
            f"duplicate operation id {conflicts[0]!r}; nothing was registered"
        )


def _register(
    dispatcher: Dispatcher,
    wanted: Sequence[HostOperation],
    operations: Sequence[BridgeOperation],
    host: _Host,
) -> None:
    """Allowlist each operation against the handler its id names.

    A declared event set is what makes an operation a stream, so the source the
    handler returns is the factory the dispatcher pumps, and a handler for a
    plain call returns the result dict instead.
    """
    streams = {operation.id for operation in wanted if operation.events is not None}
    for operation in operations:
        handler: HostHandler = partial(HANDLERS[operation.id], host)
        register = (
            dispatcher.register_bound_stream
            if operation.id in streams
            else dispatcher.register_bound
        )
        register(operation, handler)


def _selected(only: Sequence[str] | None) -> tuple[HostOperation, ...]:
    """Return the declared operations ``only`` names, refusing ids that are not declared."""
    if only is None:
        return HOST_OPERATIONS
    requested = set(only)
    declared = {operation.id for operation in HOST_OPERATIONS}
    unknown = sorted(requested - declared)
    if unknown:
        raise QgisSdkBridgeError(
            f"unknown host operation(s): {', '.join(unknown)}; "
            f"declared ids are {', '.join(sorted(declared))}"
        )
    return tuple(
        operation for operation in HOST_OPERATIONS if operation.id in requested
    )
