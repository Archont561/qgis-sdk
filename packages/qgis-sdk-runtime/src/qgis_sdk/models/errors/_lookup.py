"""Errors for a lookup that found nothing, or found it unusable.

Each one names what was asked for and what the host holds, so a caller can tell
a typo from a project that genuinely lacks the thing.
"""

from __future__ import annotations

from ._base import QgisSdkError


class QgisSdkLayerNotFoundError(QgisSdkError):
    """No layer or dataset with this identifier exists in the runtime.

    The identifier is either a layer id or a dataset location, whichever the
    caller used, so the message never claims to know which kind was meant.

    Args:
        identifier: The layer id or dataset location the caller used.
    """

    code = "layer_not_found"

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"No layer {identifier!r} is available in this runtime")


class QgisSdkLayoutNotFoundError(QgisSdkError):
    """No print layout with this name exists in the project.

    A layout is named by its own name, so the message repeats exactly what the
    caller asked for: a typo, a template that was never loaded and a project
    with no layouts at all are three answers a caller can tell apart by listing.

    Args:
        name: The layout name that was asked for.
    """

    code = "layout_not_found"

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"No print layout {name!r} is available in this project")


class QgisSdkConnectionNotFoundError(QgisSdkError):
    """No registered data-source connection answers this provider and name.

    The registry lookup (TASK-92) is over the connections QGIS keeps in its
    settings; this is unrelated to :class:`QgisSdkConnectionError`, which is a
    transport failing to reach a peer. The message names both halves so a name
    that exists under another provider is distinguishable from a name that
    exists nowhere.

    Args:
        provider: The provider the lookup was made under.
        name: The connection name, empty when the provider holds none.
    """

    code = "connection_not_found"

    def __init__(self, provider: str, name: str) -> None:
        self.provider = provider
        self.name = name
        if name:
            message = f"No connection {name!r} is registered for provider {provider!r}"
        else:
            message = f"Provider {provider!r} holds no registered connections"
        super().__init__(message)


class QgisSdkConnectionItemNotFoundError(QgisSdkError):
    """No schema, table or view with this name is in the connection.

    A browse and an open name the same ``(schema, name)`` pair, so a typo and a
    table the connection genuinely does not hold are the same refusal - the
    database decides, and this class never guesses.

    Args:
        connection: The connection that was browsed.
        schema: The schema the name was looked for in, if any.
        name: The table or view name that is not there.
    """

    code = "connection_item_not_found"

    def __init__(self, connection: str, schema: str, name: str) -> None:
        self.connection = connection
        self.schema = schema
        self.name = name
        where = f" in schema {schema!r}" if schema else ""
        super().__init__(f"No item {name!r}{where} of connection {connection!r} exists")


class QgisSdkConnectionUnavailableError(QgisSdkError):
    """A registered connection exists but its provider refused to answer.

    Different from :class:`QgisSdkConnectionNotFoundError`: the lookup
    succeeded, the database behind it did not answer its catalog. The message
    is the provider's own refusal with any ``password=`` token redacted, because
    it crosses to a page and a provider error can quote what it refused.

    Args:
        provider: The provider the connection is registered under.
        name: The connection whose catalog refused.
        detail: The provider's own message, with secrets redacted.
    """

    code = "connection_unavailable"

    def __init__(self, provider: str, name: str, detail: str) -> None:
        self.provider = provider
        self.name = name
        self.detail = detail
        super().__init__(
            f"Connection {name!r} of provider {provider!r} refused: {detail}"
        )


class QgisSdkAuthConfigNotFoundError(QgisSdkError):
    """No authentication configuration with this id is in the registry.

    The identifier is the seven-character ``authcfg`` reference QGIS spends;
    the message repeats the id, never anything the id stands for.

    Args:
        auth_config: The ``authcfg`` id that is not registered.
    """

    code = "auth_config_not_found"

    def __init__(self, auth_config: str) -> None:
        self.auth_config = auth_config
        super().__init__(
            f"No authentication configuration {auth_config!r} is registered"
        )


class QgisSdkStyleNotFoundError(QgisSdkError):
    """No reviewed style with this identifier is packaged with the SDK.

    Args:
        style: The packaged style identifier that is unknown.
    """

    code = "style_not_found"

    def __init__(self, style: str) -> None:
        self.style = style
        super().__init__(f"No packaged style {style!r} is available")


class QgisSdkThemeNotFoundError(QgisSdkError):
    """No map theme with this name exists in the project.

    The canvas keeps whatever theme it was drawn with; a page that applied a
    theme by a stale name hears which name failed rather than seeing an
    unchanged map and assuming the call went through.

    Args:
        theme: The map theme name that is not in the project.
    """

    code = "theme_not_found"

    def __init__(self, theme: str) -> None:
        self.theme = theme
        super().__init__(f"No map theme {theme!r} is available in this project")


class QgisSdkBookmarkNotFoundError(QgisSdkError):
    """No bookmark with this name exists in the project.

    Args:
        name: The bookmark name that is not in the project.
    """

    code = "bookmark_not_found"

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"No bookmark {name!r} is available in this project")


class QgisSdkRasterBandError(QgisSdkError):
    """A band number outside the raster's ``1..band_count`` range.

    ``band_count`` travels with the message so a caller that guessed hears what
    the raster actually has; nothing is read and no zeros are invented.

    Args:
        layer_id: The raster that was read.
        band: The band number the caller asked for.
        band_count: How many bands the raster actually has.
    """

    code = "raster_band_out_of_range"

    def __init__(self, layer_id: str, band: int, band_count: int) -> None:
        self.layer_id = layer_id
        self.band = band
        self.band_count = band_count
        super().__init__(
            f"Raster {layer_id!r} has {band_count} band(s); band {band} does not exist"
        )
