"""What the endpoint may be asked to do: the allowlisted operations."""

from __future__ import annotations

from typing import Any

from qgis_sdk.bridge.endpoint._refusals import refuse
from qgis_sdk.bridge.endpoint._types import (
    BoundHandler,
    BoundStreamSource,
    Handler,
)
from qgis_sdk.bridge.protocol import BridgeErrorCode, BridgeOperation
from qgis_sdk.bridge.streams import StreamSource
from qgis_sdk.models.errors import QgisSdkBridgeError


class Registry:
    """The operations a plugin exposes, and what answers each one.

    Nothing about an operation is reachable from the wire: a view names an id,
    and the handler or source bound to that id here is the only thing that can
    run. Registration is the one place that decides an id is new, so a duplicate
    is refused when the plugin is wired rather than when a call arrives.
    """

    def __init__(self) -> None:
        self._operations: dict[str, BridgeOperation] = {}
        self._handlers: dict[str, BoundHandler] = {}
        self._sources: dict[str, BoundStreamSource] = {}

    def register(self, operation: BridgeOperation, handler: Handler) -> None:
        """Allowlist one operation and bind it to its handler."""
        self._check(operation, handler, "handler")
        self._operations[operation.id] = operation
        self._handlers[operation.id] = lambda binding, payload: handler(payload)

    def register_bound(self, operation: BridgeOperation, handler: BoundHandler) -> None:
        """Allowlist one operation whose handler receives the caller's binding.

        The binding is the one the host minted for the channel the call arrived
        on; nothing in it came from the payload. This is how an operation that
        takes a scoped handle checks the handle belongs to the view using it.
        """
        self._check(operation, handler, "handler")
        self._operations[operation.id] = operation
        self._handlers[operation.id] = handler

    def register_stream(
        self, operation: BridgeOperation, factory: StreamSource
    ) -> None:
        """Allowlist one streaming operation and its source factory.

        The factory is called once per subscription with the already-checked
        payload and returns an iterator of events. Nothing about it is reachable
        from the wire: the view names an operation id, never a callable.

        A factory may return ``None`` instead, for a stream a host pushes into
        with ``emit`` rather than allows to be pulled - a Qt task reporting
        progress, for instance. Such a subscription ends when it is disposed or
        when its buffer overruns, never by itself. Or it may return a
        :class:`~qgis_sdk.bridge.streams.PushSource`, which the dispatcher
        starts with a sink once the subscription exists: the source then ends
        the stream itself when its work completes or fails.
        """
        self._check(operation, factory, "factory")
        self._operations[operation.id] = operation
        self._sources[operation.id] = lambda binding, payload: factory(payload)

    def register_bound_stream(
        self, operation: BridgeOperation, factory: BoundStreamSource
    ) -> None:
        """Allowlist one streaming operation whose factory sees the caller."""
        self._check(operation, factory, "factory")
        self._operations[operation.id] = operation
        self._sources[operation.id] = factory

    def operations(self) -> tuple[BridgeOperation, ...]:
        """Return the allowlisted operations in id order."""
        return tuple(self._operations[key] for key in sorted(self._operations))

    def operation(self, operation_id: str) -> BridgeOperation:
        """Return the declaration of an allowlisted operation."""
        return self._operations[operation_id]

    def handler_for(self, operation_id: str, call_id: str) -> BoundHandler:
        """Return the handler of an allowlisted operation, or refuse the call."""
        handler = self._handlers.get(operation_id)
        if handler is None:
            refuse(
                call_id,
                BridgeErrorCode.UNKNOWN_OPERATION,
                f"No operation {operation_id!r} is exposed by this plugin",
            )
        return handler

    def source_for(self, operation_id: str, call_id: str) -> BoundStreamSource:
        """Return the source factory of a streaming operation, or refuse the call."""
        factory = self._sources.get(operation_id)
        if factory is None:
            refuse(
                call_id,
                BridgeErrorCode.UNKNOWN_OPERATION,
                f"No streaming operation {operation_id!r} is exposed",
            )
        return factory

    def _check(self, operation: BridgeOperation, target: Any, role: str) -> None:
        if operation.id in self._handlers or operation.id in self._sources:
            raise QgisSdkBridgeError(f"duplicate operation id {operation.id!r}")
        if not callable(target):
            raise QgisSdkBridgeError(f"{operation.id}: {role} must be callable")
