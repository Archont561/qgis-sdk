"""Native connections: the provider registry QGIS keeps in its settings.

Every connection here comes from the registry the QGIS application already
owns - ``QgsProviderRegistry`` per provider, the connections each provider's
metadata stores - and every description leaves the credential material behind:

* **The URI is read and dropped.** A connection's data source URI is the one
  place a password can appear in plaintext, so the adapter parses it for the
  authentication configuration *id* (``QgsDataSourceUri.authConfigId``) and
  never lets the string itself reach a model. ``uri(expandAuthConfig=False)``
  is the only form written back on attach, and the stored password is cleared
  while doing it.
* **The authentication database is read un-decrypted.**
  ``QgsAuthManager.availableAuthMethodConfigs`` answers "base configs (not
  decrypted data)" - ids and names - and that is the whole model.
* **A GeoPackage connection answers provider ``ogr``.** The connection registry
  for GeoPackage files hangs off ``QgsOgrProviderMetadata`` (``QgsOgrProvider::
  providerKey()`` is ``ogr``; QGIS's own data items comment that "GPKG methods
  are implemented in OGR"), so ``ogr`` is the honest provider key - not
  ``geopackage``, which names no registry.

``open_layer`` maps each wired provider to the layer key its tables open with:
``postgres`` tables open through the ``postgres`` provider, GeoPackage tables
through ``ogr``. A provider outside that table is refused by name rather than
opened with a guessed key, and a raster table is refused the same way - this
operation answers a vector layer description.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from qgis.core import (
    QgsAbstractDatabaseProviderConnection,
    QgsApplication,
    QgsDataSourceUri,
    QgsProviderConnectionException,
    QgsProviderMetadata,
    QgsProviderRegistry,
    QgsVectorLayer,
    QgsWkbTypes,
)

from qgis_sdk.adapters.qgis.layers import (
    GEOMETRY_TYPES,
    NO_GEOMETRY,
    NativeLayers,
)
from qgis_sdk.models import (
    AuthConfiguration,
    ConnectionInfo,
    ConnectionItem,
    ConnectionTest,
    QgisSdkAuthConfigNotFoundError,
    QgisSdkConnectionItemNotFoundError,
    QgisSdkConnectionNotFoundError,
    QgisSdkConnectionUnavailableError,
    QgisSdkUnsupportedCapabilityError,
    VectorLayerInfo,
)

#: The provider key that opens a registry's tables as vector layers. ``ogr``
#: is where GeoPackage connections live *and* what their table URIs open with;
#: ``postgres`` is both for PostGIS. Every other provider is listed and browsed
#: but not opened by this adapter, by name.
_LAYER_PROVIDERS: dict[str, str] = {"ogr": "ogr", "postgres": "postgres"}

#: The providers whose connections spend a QGIS authentication configuration.
#: A GeoPackage connection authenticates by file access and has nothing to
#: attach; only ``postgres`` of the wired providers reads ``authcfg``.
_AUTH_PROVIDERS: frozenset[str] = frozenset({"postgres"})

#: A provider refusal can quote what it refused; a password is not crossed.
_PASSWORD = re.compile(r"password=\S+", re.IGNORECASE)


def _redact(message: str) -> str:
    return _PASSWORD.sub("password=…", message)


#: The precedence the model's docstring records, as the order the flags are
#: tested in: a materialised view is a view, a view stays a view even when it has
#: geometry, and a foreign table keeps its place last.
_ITEM_KINDS = (
    ("MaterializedView", "materialized_view"),
    ("View", "view"),
    ("Raster", "raster"),
    ("Vector", "vector"),
    ("Aspatial", "aspatial"),
)


def _item_kind(flags: object) -> str:
    """Name one table the way ``CONNECTION_ITEM_KINDS`` declares the order.

    Both backends answer alike because both walk the same table: the order is
    data here rather than a chain of guards, so a new flag is a row.
    """
    table_flag = QgsAbstractDatabaseProviderConnection.TableFlag
    for name, kind in _ITEM_KINDS:
        if flags & getattr(table_flag, name):  # type: ignore[operator]
            return kind
    return "foreign"


def _geometries(property: object) -> tuple[str, ...]:
    """The table's geometry columns in the layer vocabulary, in order.

    A provider may name a geometry column that holds no geometry - an
    aspatial table, whose single ``NoGeometry`` column is a column and not a
    kind - and that column is left out rather than answering ``"none"``: the
    vocabulary has no such kind, and the fake's aspatial tables answer ``()``.
    """
    found: list[str] = []
    for column in property.geometryColumnTypes():  # type: ignore[attr-defined]
        geometry = GEOMETRY_TYPES.get(
            QgsWkbTypes.geometryType(column.wkbType), NO_GEOMETRY
        )
        if geometry == NO_GEOMETRY:
            continue
        if geometry not in found:
            found.append(geometry)
    return tuple(found)


class NativeConnections:
    """The ``Connections`` protocol over QGIS's own connection registry.

    Ownership: layers this adapter opens land in the sibling
    :class:`NativeLayers` registry and are released with its scope; the
    connection registry itself is QGIS's, and attaching an authentication
    configuration writes back through ``saveConnection`` - the one write this
    surface owns, which is why it is annotated ``destructive`` on the wire.
    """

    def __init__(self, layers: NativeLayers) -> None:
        self._layers = layers

    def list_connections(self) -> tuple[ConnectionInfo, ...]:
        found: list[ConnectionInfo] = []
        for provider in QgsProviderRegistry.instance().providerList():
            try:
                registered = self._metadata(provider).dbConnections(False)
            except QgsProviderConnectionException:
                # One registry QGIS cannot read must not hide the rest.
                continue
            for name in sorted(registered):
                found.append(self._info(provider, name, registered[name]))
        return tuple(found)

    def connection(self, provider: str, name: str) -> ConnectionInfo:
        connection = self._require(provider, name)
        return self._info(provider, name, connection)

    def browse(
        self, provider: str, name: str, schema: str | None = None
    ) -> tuple[ConnectionItem, ...]:
        connection = self._require(provider, name)
        schemas = self._catalog(connection, provider, name)
        if not schema:
            if schemas:
                return tuple(
                    ConnectionItem(name=each, schema="", kind="schema")
                    for each in schemas
                )
            return self._tables(connection, provider, name, "")
        if schema not in schemas:
            raise QgisSdkConnectionItemNotFoundError(name, schema, "")
        return self._tables(connection, provider, name, schema)

    def open_layer(
        self, provider: str, name: str, schema: str, item: str
    ) -> VectorLayerInfo:
        connection = self._require(provider, name)
        schemas = self._catalog(connection, provider, name)
        try:
            property = connection.table(schema or "", item)
        except QgsProviderConnectionException as error:
            # No table answers: a schema name passed as the item is refused as
            # what it is, not as a typo - the same rule the fake applies.
            if not schema and item in schemas:
                raise QgisSdkUnsupportedCapabilityError(
                    "connections.open_layer",
                    "a schema is browsed, not opened",
                ) from error
            raise QgisSdkConnectionItemNotFoundError(
                name, schema or "", item
            ) from error
        if _item_kind(property.flags()) == "raster":
            raise QgisSdkUnsupportedCapabilityError(
                "connections.open_layer",
                "a raster table is opened by its raster provider, not "
                "described as a vector layer",
            )
        layer_provider = _LAYER_PROVIDERS.get(provider)
        if layer_provider is None:
            raise QgisSdkUnsupportedCapabilityError(
                "connections.open_layer",
                f"tables of provider {provider!r} are not opened by this SDK",
            )
        try:
            uri = connection.tableUri(schema or "", item)
        except QgsProviderConnectionException as error:
            raise QgisSdkConnectionItemNotFoundError(
                name, schema or "", item
            ) from error
        layer = QgsVectorLayer(uri, item, layer_provider)
        if not layer.isValid():
            raise QgisSdkConnectionItemNotFoundError(name, schema or "", item)
        return self._described(layer)

    def _described(self, layer: Any) -> VectorLayerInfo:
        """Adopt the table and describe its fields without the FID column.

        A provider may report the column that identifies a feature as an
        ordinary field - the GeoPackage fixture's ``fid INTEGER PRIMARY
        KEY`` answers ``("fid", "name")`` where the table has one field -
        and the fake's tables declare no such field. The row identity is
        not a field of the row, so the primary-key attributes are left out
        of the description the caller reads.
        """
        info = self._layers.adopt_vector(layer)
        primary = set()
        provider = layer.dataProvider()
        if provider is not None:
            primary = set(provider.pkAttributeIndexes())
        if not primary:
            return info
        names = tuple(
            field_name
            for index, field_name in enumerate(layer.fields().names())
            if index not in primary
        )
        return replace(info, field_names=names)

    def test(self, provider: str, name: str) -> ConnectionTest:
        connection = self._require(provider, name)
        try:
            self._catalog(connection, provider, name)
        except QgisSdkConnectionUnavailableError as error:
            return ConnectionTest(valid=False, message=str(error))
        return ConnectionTest(valid=True)

    def auth_configurations(self) -> tuple[AuthConfiguration, ...]:
        found = QgsApplication.authManager().availableAuthMethodConfigs()
        return tuple(
            # A nameless configuration exists and is spendable, so it is
            # described by its id rather than hidden.
            AuthConfiguration(id=key, name=config.name() or key)
            for key, config in sorted(found.items())
        )

    def attach_auth_config(self, provider: str, name: str, auth_config: str) -> None:
        connection = self._require(provider, name)
        if auth_config not in QgsApplication.authManager().configIds():
            raise QgisSdkAuthConfigNotFoundError(auth_config)
        if provider not in _AUTH_PROVIDERS:
            raise QgisSdkUnsupportedCapabilityError(
                "auth.attach",
                f"connection {name!r} of provider {provider!r} authenticates "
                "without a configuration; there is none to attach",
            )
        uri = QgsDataSourceUri(connection.uri())
        # The configuration replaces how the connection authenticates: the
        # stored password stops being stored and stops being spent. The write
        # back is the non-expanded form - ``authcfg=…`` and no secret.
        uri.setPassword("")
        uri.setAuthConfigId(auth_config)
        connection.setUri(uri.uri(False))
        self._metadata(provider).saveConnection(connection, name)

    # -- registry lookups -----------------------------------------------------

    def _metadata(self, provider: str) -> QgsProviderMetadata:
        metadata = QgsProviderRegistry.instance().providerMetadata(provider)
        if metadata is None:
            raise QgisSdkConnectionNotFoundError(provider, "")
        return metadata

    def _require(self, provider: str, name: str) -> Any:
        try:
            registered = self._metadata(provider).dbConnections(False)
        except QgsProviderConnectionException as error:
            raise QgisSdkConnectionUnavailableError(
                provider, name, _redact(str(error))
            ) from error
        connection = registered.get(name)
        if connection is None:
            raise QgisSdkConnectionNotFoundError(provider, name)
        return connection

    def _catalog(self, connection: Any, provider: str, name: str) -> tuple[str, ...]:
        """Answer the connection's schemas, proving the database answers.

        A schema-less backend - the ``ogr`` connection that answers a
        GeoPackage file, whose provider refuses ``Schemas`` outright - is not
        an unavailable one: the refusal is answered by listing its tables, and
        only a table listing that also refuses makes the connection
        unavailable. An empty answer stays empty either way, so ``browse``
        lists those tables directly.
        """
        try:
            schemas = tuple(connection.schemas())
        except QgsProviderConnectionException as error:
            try:
                connection.tables()
            except QgsProviderConnectionException:
                raise QgisSdkConnectionUnavailableError(
                    provider, name, _redact(str(error))
                ) from error
            return ()
        if not schemas:
            # `schemas()` is a no-op there and would pass a missing file.
            try:
                connection.tables()
            except QgsProviderConnectionException as error:
                raise QgisSdkConnectionUnavailableError(
                    provider, name, _redact(str(error))
                ) from error
        return schemas

    def _tables(
        self, connection: Any, provider: str, name: str, schema: str
    ) -> tuple[ConnectionItem, ...]:
        try:
            properties = connection.tables(schema)
        except QgsProviderConnectionException as error:
            # The catalog answered, so this listing is a refusal, not a miss.
            raise QgisSdkConnectionUnavailableError(
                provider, name, _redact(str(error))
            ) from error
        return tuple(
            ConnectionItem(
                name=property.tableName(),
                schema=property.schema(),
                kind=_item_kind(property.flags()),
                geometries=_geometries(property),
            )
            for property in properties
        )

    def _info(self, provider: str, name: str, connection: Any) -> ConnectionInfo:
        auth_config = QgsDataSourceUri(connection.uri()).authConfigId()
        return ConnectionInfo(
            name=name,
            provider=provider,
            auth_config=auth_config or None,
        )
