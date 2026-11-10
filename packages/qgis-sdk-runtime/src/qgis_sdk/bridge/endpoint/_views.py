"""Who may call what: bindings, generations, the handshake and its reply."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qgis_sdk.bridge.endpoint._refusals import refuse
from qgis_sdk.bridge.endpoint._registry import _Registry
from qgis_sdk.bridge.endpoint._types import (
    Authorizer,
    ThemeProvider,
    ViewBinding,
    Waker,
)
from qgis_sdk.bridge.protocol import (
    BRIDGE_PROTOCOL_VERSION,
    HOST_SCHEMA_VERSION,
    BridgeErrorCode,
    peek_call_id,
    success,
    to_wire,
)
from qgis_sdk.models.errors import QgisSdkBridgeError

_STALE = "This view belongs to a runtime generation that no longer exists"
_NOT_AUTHORIZED = "This view is not authorized for that operation"


class _Views:
    """Every view the host has bound, and what each of them may do.

    A binding is minted here and never read from a payload; the generation it
    carries is what makes a view's traffic expire with the runtime that served
    it. Authorization runs before the allowlist lookup - a caller that may not do
    a thing should not learn whether the host could have done it - which is why
    :meth:`require` answers a forbidden call and an unknown one with the same
    code, and only a caller allowed to learn the difference sees one.
    """

    def __init__(
        self,
        *,
        description: Mapping[str, Any] | None,
        authorize: Authorizer | None,
        theme: ThemeProvider | None,
        registry: _Registry,
    ) -> None:
        self._description = None if description is None else to_wire(description)
        self._authorize = authorize
        self._theme = theme
        self._registry = registry
        self._wakers: dict[str, Waker] = {}
        self._generation = 0

    @property
    def generation(self) -> int:
        """The runtime generation every live binding must match."""
        return self._generation

    def advance(self) -> int:
        """Start a new generation, invalidating every binding minted so far.

        A view that reconnects gets a fresh binding; one that keeps using the old
        one is refused with ``stale_generation`` rather than served state from a
        runtime that no longer exists.
        """
        self._generation += 1
        return self._generation

    def bind(self, *, view_id: str, origin: str) -> ViewBinding:
        """Mint the binding for a view that just connected."""
        if not isinstance(view_id, str) or not view_id.strip():
            raise QgisSdkBridgeError("view_id must be a nonempty string")
        if not isinstance(origin, str) or not origin.strip():
            raise QgisSdkBridgeError("origin must be a nonempty string")
        return ViewBinding(view_id=view_id, origin=origin, generation=self._generation)

    def watch(self, binding: ViewBinding, wake: Waker) -> None:
        """Ask to be woken when a pushed stream queues frames for this view.

        A channel adapter registers its flush here, so a reply that arrives on
        a later event loop turn reaches the page without anyone polling. One
        waker per view: a new channel for the same view replaces the old one.
        """
        self._wakers[binding.view_id] = wake

    def unwatch(self, binding: ViewBinding) -> None:
        """Stop waking this view; a wake after this is simply not delivered."""
        self._wakers.pop(binding.view_id, None)

    def waker_for(self, view_id: str) -> Waker:
        """Return a wake callback that looks the view's waker up when it fires.

        Looked up late on purpose: a channel registered after the subscription
        opened still gets woken, and one that unwatched is left alone.
        """

        def wake() -> None:
            waker = self._wakers.get(view_id)
            if waker is not None:
                waker()

        return wake

    def handshake(self, *, view_id: str, origin: str) -> tuple[ViewBinding, dict]:
        """Bind a view and return the reply that completes the handshake.

        The reply carries the protocol version, the generation the view must
        present later through the host (never through the payload), and the
        plugin description so the frontend can render forms without a second
        call.
        """
        binding = self.bind(view_id=view_id, origin=origin)
        return binding, to_wire(self._full_reply(binding))

    def reply(self, binding: ViewBinding, raw: Mapping[str, Any]) -> dict[str, Any]:
        """Answer ``kind: "handshake"`` for a view the host already bound.

        A page connected through QWebChannel never minted its own binding - the
        adapter did, before the first message - so it asks for the contract
        with a call instead. The reply is the one :meth:`handshake` builds,
        narrowed to the operations this view is authorized to call: what it
        lists is exactly what ``qgis.host.granted`` may show.
        """
        call_id = peek_call_id(raw) or ""
        self.require_live(binding, call_id)
        reply = self._full_reply(
            binding,
            operations=[
                operation.to_dict()
                for operation in self._registry.operations()
                if self.is_authorized(binding, operation.id)
            ],
        )
        return success(call_id, to_wire(reply))

    def theme_entry(self) -> dict[str, Any]:
        """``{"theme": ...}`` when the provider has a palette, nothing otherwise."""
        if self._theme is None:
            return {}
        theme = self._theme()
        return {} if theme is None else {"theme": dict(theme)}

    def require(self, binding: ViewBinding, operation: str, call_id: str) -> None:
        """Refuse a call this view may not make; return quietly when it may."""
        self.require_live(binding, call_id)
        self.require_authorized(binding, operation, call_id)

    def require_live(self, binding: ViewBinding, call_id: str) -> None:
        """Refuse a call from a view whose runtime generation is gone."""
        if binding.generation != self._generation:
            refuse(call_id, BridgeErrorCode.STALE_GENERATION, _STALE)

    def require_authorized(
        self,
        binding: ViewBinding,
        operation: str,
        call_id: str,
        *,
        reason: str = _NOT_AUTHORIZED,
    ) -> None:
        """Refuse a call this view is not authorized for."""
        if not self.is_authorized(binding, operation):
            refuse(call_id, BridgeErrorCode.NOT_AUTHORIZED, reason)

    def is_authorized(self, binding: ViewBinding, operation: str) -> bool:
        """Whether the host's authorizer allows this view to call ``operation``."""
        if self._authorize is None:
            return False
        return bool(self._authorize(binding, operation))

    def _full_reply(
        self, binding: ViewBinding, *, operations: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """The handshake reply, listing every operation unless told otherwise."""
        listed = (
            [operation.to_dict() for operation in self._registry.operations()]
            if operations is None
            else operations
        )
        return {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "generation": binding.generation,
            "plugin": self._description,
            "host_schema_version": HOST_SCHEMA_VERSION,
            "operations": listed,
            **self.theme_entry(),
        }
