from __future__ import annotations

from pathlib import Path

from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.models import (
    AuthConfiguration,
    ConnectionInfo,
    ConnectionItem,
    ConnectionTest,
    QgisSdkAuthConfigNotFoundError,
    QgisSdkConnectionItemNotFoundError,
    QgisSdkConnectionNotFoundError,
    QgisSdkUnsupportedCapabilityError,
    VectorLayerInfo,
)

from ._declarations import (
    ConnectionDeclaration,
    TableDeclaration,
    VectorLayerDeclaration,
)
from ._layers import FakeLayers
from ._styles import missing_table, refuse_unopenable, table_entry


class FakeConnections:
    """A ``Connections`` backend over connections declared in the test.

    The fake stores descriptions and answers from them, and its one piece of
    real behaviour is the same the native adapter enforces: **nothing secret is
    stored or answered**. A declaration carries an authentication configuration
    *id*, never the material behind it, and :meth:`attach_auth_config` swaps the
    id the description answers - which is what "attaching" means at this
    boundary.

    A declaration also says what the fake will not pretend: ``valid=False``
    makes :meth:`test` answer the refusal (a message the test wrote, because
    the fake has no provider to refuse with) and ``accepts_auth=False`` makes
    attachment fail the way a file-based connection's does natively.
    """

    def __init__(self, layers: FakeLayers) -> None:
        """Build the connection fake over the layer backend it opens through.

        Args:
            layers: The layer backend the browsed tables are opened on.
        """
        self._layers = layers
        self._connections: dict[tuple[str, str], dict[str, object]] = {}
        self._tables: dict[tuple[str, str], list[dict[str, object]]] = {}
        self._auth: dict[str, AuthConfiguration] = {}
        self._opened = 0

    def declare_connection(self, declaration: ConnectionDeclaration) -> None:
        """Declare one registered connection and the schemas it browses to.

        Args:
            declaration: The connection the fake answers for.
        """
        key = (declaration.provider, declaration.name)
        self._connections[key] = {
            "auth_config": declaration.auth_config,
            "schemas": tuple(declaration.schemas),
            "valid": declaration.valid,
            "message": declaration.message,
            "accepts_auth": declaration.accepts_auth,
        }
        self._tables.setdefault(key, [])

    def declare_table(self, declaration: TableDeclaration) -> None:
        """Declare one table or view inside a declared connection.

        Args:
            declaration: The table or view the fake answers for.
        """
        key = (declaration.provider, declaration.connection)
        if key not in self._connections:
            raise QgisSdkDeclarationError(
                f"connection {declaration.connection!r} of provider "
                f"{declaration.provider!r} is not declared before its tables"
            )
        self._tables[key].append(table_entry(declaration))

    def declare_auth_configuration(self, name: str) -> str:
        """Declare one authentication configuration and answer its id.

        The id is the registry's to choose here exactly as it is natively
        (``QgsAuthManager`` assigns one), so a test keeps the id it is handed
        and never writes one it expects back.

        Args:
            name: The name the configuration is registered under.
        """
        auth_config = f"cfg{len(self._auth) + 1:04d}"
        self._auth[auth_config] = AuthConfiguration(id=auth_config, name=name)
        return auth_config

    def list_connections(self) -> tuple[ConnectionInfo, ...]:
        return tuple(self._describe(key) for key in self._connections)

    def connection(self, provider: str, name: str) -> ConnectionInfo:
        """The description of one declared connection.

        Args:
            provider: The provider the connection is registered under.
            name: The connection name.
        """
        self._require(provider, name)
        return self._describe((provider, name))

    def browse(
        self, provider: str, name: str, schema: str | None = None
    ) -> tuple[ConnectionItem, ...]:
        """The items one declared connection holds.

        Args:
            provider: The provider the connection is registered under.
            name: The connection name.
            schema: The schema to list, or ``None`` for the root.
        """
        key = self._require(provider, name)
        declared = self._connections[key]
        schemas: tuple[str, ...] = declared["schemas"]  # type: ignore[assignment]
        if not schema:
            if schemas:
                return tuple(
                    ConnectionItem(name=each, schema="", kind="schema")
                    for each in schemas
                )
            return tuple(entry["item"] for entry in self._tables[key])  # type: ignore[misc]
        if schema not in schemas:
            raise QgisSdkConnectionItemNotFoundError(name, schema, "")
        return tuple(
            entry["item"]  # type: ignore[misc]
            for entry in self._tables[key]
            if entry["item"].schema == schema  # type: ignore[union-attr]
        )

    def open_layer(
        self, provider: str, name: str, schema: str, item: str
    ) -> VectorLayerInfo:
        """The layer one declared table answers with.

        Args:
            provider: The provider the connection is registered under.
            name: The connection name.
            schema: The schema the item lives in.
            item: The table or view to open.
        """
        key = self._require(provider, name)
        for entry in self._tables[key]:
            declared: ConnectionItem = entry["item"]  # type: ignore[assignment]
            if declared.name != item or declared.schema != (schema or ""):
                continue
            refuse_unopenable(declared.kind)
            self._opened += 1
            source = Path(f"fake-connection:{provider}:{name}:{schema or '-'}:{item}")
            declare_table(self._layers, source, item, declared, entry)
            return self._layers.open_vector(source)
        return missing_table(self, key, name, schema, item)

    def test(self, provider: str, name: str) -> ConnectionTest:
        """Whether one declared connection opens.

        Args:
            provider: The provider the connection is registered under.
            name: The connection name.
        """
        key = self._require(provider, name)
        declared = self._connections[key]
        if declared["valid"]:
            return ConnectionTest(valid=True)
        message = declared["message"] or "the declared connection does not answer"
        return ConnectionTest(valid=False, message=str(message))

    def auth_configurations(self) -> tuple[AuthConfiguration, ...]:
        return tuple(self._auth.values())

    def attach_auth_config(self, provider: str, name: str, auth_config: str) -> None:
        """Point one declared connection at an auth configuration.

        Args:
            provider: The provider the connection is registered under.
            name: The connection name.
            auth_config: The ``authcfg`` id to attach.
        """
        key = self._require(provider, name)
        if auth_config not in self._auth:
            raise QgisSdkAuthConfigNotFoundError(auth_config)
        declared = self._connections[key]
        if not declared["accepts_auth"]:
            raise QgisSdkUnsupportedCapabilityError(
                "auth.attach",
                f"connection {name!r} of provider {provider!r} authenticates "
                "without a configuration; there is none to attach",
            )
        declared["auth_config"] = auth_config

    def _require(self, provider: str, name: str) -> tuple[str, str]:
        key = (provider, name)
        if key not in self._connections:
            raise QgisSdkConnectionNotFoundError(provider, name)
        return key

    def _describe(self, key: tuple[str, str]) -> ConnectionInfo:
        declared = self._connections[key]
        return ConnectionInfo(
            name=key[1],
            provider=key[0],
            auth_config=declared["auth_config"],  # type: ignore[arg-type]
        )


def declare_table(
    layers: FakeLayers,
    source: Path,
    item: str,
    declared: ConnectionItem,
    entry: dict[str, object],
) -> None:
    """Declare one browsed table's dataset so opening it answers a layer.

    Args:
        layers: The layer fake the dataset is declared on.
        source: The dataset path the table is opened by.
        item: The table or view name the layer is named after.
        declared: The browse item the connection answered with.
        entry: The table's other declared values, its fields and CRS.
    """
    fields: tuple[str, ...] = entry["fields"]  # type: ignore[assignment]
    layers.register(
        VectorLayerDeclaration(
            source,
            name=item,
            geometry_type=(declared.geometries[0] if declared.geometries else "none"),
            field_names=fields,
            crs=entry["crs"],  # type: ignore[arg-type]
        )
    )
