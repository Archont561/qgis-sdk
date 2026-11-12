"""Expected failures that callers can distinguish without importing QGIS."""

from collections.abc import Iterable
from dataclasses import dataclass


class QgisSdkError(Exception):
    """Base class for expected SDK errors; adapters may translate its code."""

    code = "sdk_error"


class QgisSdkScopeClosedError(QgisSdkError):
    """An operation attempted to use an already disposed owner scope."""

    code = "scope_closed"

    def __init__(self) -> None:
        super().__init__("This resource scope has been disposed")


class QgisSdkUnsupportedCapabilityError(QgisSdkError):
    """The selected runtime does not offer an explicitly requested capability.

    ``reason`` is set when the capability exists elsewhere in the same runtime
    but not *here* - a worker thread, for example, which must not touch the
    project the driving thread owns (decision-65). The message then says why
    instead of only that the host lacks the service.
    """

    code = "unsupported_capability"

    def __init__(self, capability: str, reason: str | None = None) -> None:
        self.capability = capability
        self.reason = reason
        message = f"Capability {capability!r} is unavailable in this runtime"
        if reason is not None:
            message = f"Capability {capability!r} is unavailable here: {reason}"
        super().__init__(message)


class QgisSdkOptionalDependencyError(QgisSdkError):
    """An explicitly selected adapter needs an administrator-provisioned package."""

    code = "optional_dependency_unavailable"

    def __init__(self, dependency: str, installation_hint: str) -> None:
        self.dependency = dependency
        self.installation_hint = installation_hint
        super().__init__(
            f"Optional dependency {dependency!r} is unavailable. {installation_hint}"
        )


class QgisSdkLayerNotFoundError(QgisSdkError):
    """No layer or dataset with this identifier exists in the runtime.

    The identifier is either a layer id or a dataset location, whichever the
    caller used, so the message never claims to know which kind was meant.
    """

    code = "layer_not_found"

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"No layer {identifier!r} is available in this runtime")


class QgisSdkStyleIncompatibleError(QgisSdkError):
    """A packaged style cannot be applied to the target layer.

    Reasons are short, user-readable statements about the mismatch that was
    detected, never the rejected layer object.
    """

    code = "style_incompatible"

    def __init__(
        self,
        layer_id: str,
        style: str,
        reasons: Iterable[str],
    ) -> None:
        self.layer_id = layer_id
        self.style = style
        self.reasons = tuple(reasons)
        listed = "; ".join(self.reasons)
        super().__init__(
            f"Style {style!r} is incompatible with layer {layer_id!r}: {listed}"
        )


class QgisSdkLayoutNotFoundError(QgisSdkError):
    """No print layout with this name exists in the project.

    A layout is named by its own name, so the message repeats exactly what the
    caller asked for: a typo, a template that was never loaded and a project
    with no layouts at all are three answers a caller can tell apart by listing.
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
    """

    code = "auth_config_not_found"

    def __init__(self, auth_config: str) -> None:
        self.auth_config = auth_config
        super().__init__(
            f"No authentication configuration {auth_config!r} is registered"
        )


class QgisSdkStyleTextError(QgisSdkError):
    """A style document could not be read in the dialect the caller named.

    QML and SLD are two different documents, and a host that guessed which one it
    was handed would fail somewhere inside QGIS with a message about an XML node
    nobody asked for. The caller says which dialect its text is; a document that
    is not one raises this, with the format and the reason the reader gave.
    """

    code = "style_text_rejected"

    def __init__(self, format: str, detail: str) -> None:
        self.format = format
        self.detail = detail
        super().__init__(
            f"The style text is not a readable {format} document: {detail}"
        )


class QgisSdkStyleNotFoundError(QgisSdkError):
    """No reviewed style with this identifier is packaged with the SDK."""

    code = "style_not_found"

    def __init__(self, style: str) -> None:
        self.style = style
        super().__init__(f"No packaged style {style!r} is available")


class QgisSdkThemeNotFoundError(QgisSdkError):
    """No map theme with this name exists in the project.

    The canvas keeps whatever theme it was drawn with; a page that applied a
    theme by a stale name hears which name failed rather than seeing an
    unchanged map and assuming the call went through.
    """

    code = "theme_not_found"

    def __init__(self, theme: str) -> None:
        self.theme = theme
        super().__init__(f"No map theme {theme!r} is available in this project")


class QgisSdkRasterBandError(QgisSdkError):
    """A band number outside the raster's ``1..band_count`` range.

    ``band_count`` travels with the message so a caller that guessed hears what
    the raster actually has; nothing is read and no zeros are invented.
    """

    code = "raster_band_out_of_range"

    def __init__(self, layer_id: str, band: int, band_count: int) -> None:
        self.layer_id = layer_id
        self.band = band
        self.band_count = band_count
        super().__init__(
            f"Raster {layer_id!r} has {band_count} band(s); band {band} does not exist"
        )


class QgisSdkProjectFileError(QgisSdkError):
    """A project file could not be read, written or saved.

    ``detail`` is the host's own message when it gave one. A failed write leaves
    the previous file in place: the project is written to a staged path and
    replaces its destination only after the writer finished.
    """

    code = "project_file_error"

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"Project file {path!r}: {detail}")


class QgisSdkBookmarkNotFoundError(QgisSdkError):
    """No bookmark with this name exists in the project."""

    code = "bookmark_not_found"

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"No bookmark {name!r} is available in this project")


class QgisSdkExportRefusedError(QgisSdkError):
    """An export cannot start as requested: the destination fails a precondition.

    Nothing has been written when this is raised. Every reason is reported at
    once - an unknown format, a missing directory and an existing file without
    ``overwrite`` are three separate statements, not three round trips.
    """

    code = "export_refused"

    def __init__(self, destination: str, reasons: Iterable[str]) -> None:
        self.destination = destination
        self.reasons = tuple(reasons)
        listed = "; ".join(self.reasons)
        super().__init__(f"Export to {destination!r} refused: {listed}")


class QgisSdkExportFailedError(QgisSdkError):
    """The writer failed after the export started; the partial file is gone.

    ``detail`` is the writer's own message. The destination was either never
    created or, with ``overwrite``, still holds its previous content: the new
    file is committed only after the writer finished.
    """

    code = "export_failed"

    def __init__(self, destination: str, detail: str) -> None:
        self.destination = destination
        self.detail = detail
        super().__init__(f"Export to {destination!r} failed: {detail}")


class QgisSdkPackagedResourceError(QgisSdkError):
    """A resource the package must ship is missing or unusable.

    This is a packaging defect, not a caller mistake: the style was requested by
    a known identifier and the layer was already found compatible.
    """

    code = "packaged_resource_unavailable"

    def __init__(self, style: str, detail: str) -> None:
        self.style = style
        self.detail = detail
        super().__init__(f"Packaged style {style!r} could not be used: {detail}")


@dataclass(frozen=True, slots=True)
class QgisSdkValidationIssue:
    """Safe, structured location and category for a rejected contract value."""

    path: tuple[str | int, ...]
    code: str

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible issue without including the rejected value."""
        return {"path": list(self.path), "code": self.code}
