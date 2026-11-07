"""Registered data-source connections, browsing and authentication configs.

decision-54 point 4 asks for the provider connection registry QGIS keeps in its
settings to be readable by a plugin: ``connections.list``/``describe``/
``browse``/``open_layer``/``test`` and ``auth.configurations`` as ids and names
only. Two rules shape every method here:

* **No secret crosses this boundary.** A connection description is a name, a
  provider and an authentication configuration *id*; a configuration is an id
  and a name. The connection URI - the one place a password can appear in
  plaintext - and the decrypted contents of the authentication database are
  read by the native adapter and dropped before a model is built. A backend
  that answers either has broken its contract, which is what the contract
  tests assert.
* **A lookup miss is named, not guessed.** An unknown provider or connection
  raises :class:`QgisSdkConnectionNotFoundError`; an unknown schema or table
  raises :class:`QgisSdkConnectionItemNotFoundError`; a browse entry that
  cannot be opened raises ``QgisSdkUnsupportedCapabilityError`` naming its
  kind. A test of a *known* connection is different: a database that refuses
  to answer is the answer, so :meth:`Connections.test` returns a
  :class:`ConnectionTest` verdict instead of raising.

The service acts on the **database** connections of every provider that has
them (a GeoPackage file, a PostGIS database). A provider's non-database
connections - a WMS storefront, say - are out of this surface: they have no
schemas, no tables and nothing to open as a feature layer.
"""

from __future__ import annotations

from typing import Protocol

from qgis_sdk.models.connections import (
    AuthConfiguration,
    ConnectionInfo,
    ConnectionItem,
    ConnectionTest,
)
from qgis_sdk.models.layers import VectorLayerInfo


class Connections(Protocol):
    """Read the connection registry and open what it holds.

    ``provider`` is the provider key that owns the registry - ``geopackage``,
    ``postgres`` - and ``name`` is the registry key the user gave the
    connection. The pair identifies a connection the way QGIS's own dialogs
    group them; names are unique per provider, not globally.
    """

    def list_connections(self) -> tuple[ConnectionInfo, ...]:
        """Every registered database connection, across every provider.

        The order is the provider registry's, stable between calls. A provider
        whose connections cannot be read is skipped rather than failing the
        listing: one broken registry entry must not hide the rest.
        """

    def connection(self, provider: str, name: str) -> ConnectionInfo:
        """Describe one registered connection.

        Raises ``QgisSdkConnectionNotFoundError`` when the provider or the name
        is unknown - the message says which half missed.
        """

    def browse(
        self, provider: str, name: str, schema: str | None = None
    ) -> tuple[ConnectionItem, ...]:
        """List what a connection holds, one level at a time.

        With ``schema`` omitted, a backend that has schemas answers its schema
        entries (``kind="schema"``) and a backend that has none - a GeoPackage -
        answers its tables directly. With ``schema`` named, that schema's tables
        and views are answered. Raises ``QgisSdkConnectionNotFoundError`` for an
        unknown connection and ``QgisSdkConnectionItemNotFoundError`` for a
        schema the connection does not hold.
        """

    def open_layer(
        self, provider: str, name: str, schema: str, item: str
    ) -> VectorLayerInfo:
        """Open one browse entry as a vector layer and describe it.

        The layer is opened the way the provider opens it and lands in the
        runtime's layer registry like any other opened layer. A schema entry is
        refused (``QgisSdkUnsupportedCapabilityError``: "a schema is browsed,
        not opened") and so is a raster table (the same refusal naming
        ``raster``): this operation answers a vector layer description, and a
        raster table names a different provider and a different description.
        Raises ``QgisSdkConnectionItemNotFoundError`` for an entry the
        connection does not hold.
        """

    def test(self, provider: str, name: str) -> ConnectionTest:
        """Ask the provider whether the connection answers.

        A known connection that fails to authenticate or is unreachable answers
        ``ConnectionTest(valid=False, message=...)`` with the provider's
        refusal - never an exception, because "this connection is broken" is
        the answer the call exists to give. Raises
        ``QgisSdkConnectionNotFoundError`` only for a lookup miss.
        """

    def auth_configurations(self) -> tuple[AuthConfiguration, ...]:
        """Every authentication configuration, as an id and a name.

        The authentication database's decrypted contents are never read: QGIS
        answers base configurations (ids and names) and this is the whole
        model. The order is the registry's.
        """

    def attach_auth_config(self, provider: str, name: str, auth_config: str) -> None:
        """Attach one authentication configuration to one registered connection.

        This replaces how the connection authenticates - the old password or
        configuration stops being spent the moment the new id is stored - which
        is why the host operation is annotated ``destructive``. Raises
        ``QgisSdkAuthConfigNotFoundError`` for an id the registry does not
        hold, ``QgisSdkConnectionNotFoundError`` for an unknown connection and
        ``QgisSdkUnsupportedCapabilityError`` for a connection that
        authenticates without one (a GeoPackage is opened by file access).
        """
