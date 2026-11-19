"""What a host has to offer: the three registration calls, and nothing else.

The real object is a ``QgsServerInterface`` in ``qgis_sdk.adapters.qgis.server``;
``qgis_sdk.testing`` scripts one. Both are registered with the same three calls,
so the dispatcher is the same code in a test and in a deployed server.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

__all__ = ["ServerInterface"]


class ServerInterface(Protocol):
    """What the host needs of a ``QgsServerInterface``, and all it needs.

    The real object lives in the adapter and the scripted one in
    ``qgis_sdk.testing``; both are registered with the same three calls, so the
    dispatcher below is the same code in a test and in a deployed server.
    """

    def register_filter(
        self,
        name: str,
        hook: Callable[..., Any],
        priority: int,
    ) -> None:
        """Register a request hook under ``name`` at ``priority``.

        Args:
            name: The registration's identity, which a re-register compares by.
            hook: The filter function.
            priority: The order QGIS calls it in; lower runs first.
        """

    def register_service(
        self,
        name: str,
        version: str,
        handler: Callable[..., Any],
    ) -> None:
        """Register the handler of the OGC service ``name`` at ``version``.

        Args:
            name: The service name the ``SERVICE`` parameter is matched against.
            version: The version QGIS advertises in its service registry.
            handler: The service function.
        """

    def register_access_control(
        self,
        name: str,
        hook: Callable[..., Any],
        priority: int,
    ) -> None:
        """Register a layer permission hook under ``name`` at ``priority``.

        Args:
            name: The registration's identity.
            hook: The access-control function.
            priority: The order QGIS calls it in; lower runs first.
        """
