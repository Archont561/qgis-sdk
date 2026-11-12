from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from qgis_sdk.core import ResourceScope
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.models import (
    STYLE_MANAGER_KINDS,
    SYMBOLS_FOR_GEOMETRY,
    ConnectionItem,
    FillSymbol,
    Labelling,
    LineSymbol,
    MarkerSymbol,
    QgisSdkConnectionItemNotFoundError,
    QgisSdkStyleIncompatibleError,
    QgisSdkStyleTextError,
    QgisSdkUnsupportedCapabilityError,
    Renderer,
    SingleSymbolRenderer,
    StyleEntry,
    StyleText,
    VectorLayerInfo,
    renderer_from_wire,
    symbol_fits_geometry,
)
from qgis_sdk.resources import require_style
from qgis_sdk.services import (
    Layers,
    LogBase,
    LogRecord,
    Notification,
    NotificationsBase,
)

from ._declarations import TableDeclaration

if TYPE_CHECKING:
    from qgis_sdk.providers import Provider


class FakeStyles:
    """A ``Styles`` backend that validates with the shared catalog rule.

    It deliberately does not emulate *rendering*: it applies the same
    ``StyleSpec.incompatibilities`` decision the native adapter makes, then
    records the application so a pure test can observe it.

    The symbology half stores the description it was given and answers it back,
    which is what makes a round trip one assertion in a plugin's own tests; a
    layer nobody has styled answers the renderer its geometry implies, so a test
    that never set anything still reads a description rather than ``None``. QML
    and SLD are modelled as the same documented JSON document with a dialect on
    it: the fake round-trips *its own* text and refuses text it did not write,
    and the native adapter is where the real QGIS dialects are proven.
    """

    def __init__(
        self,
        layers: Layers,
        scope: ResourceScope,
        *,
        styles: Sequence[StyleEntry] = (),
    ) -> None:
        self._layers = layers
        self._scope = scope
        self._applied: dict[str, list[str]] = {}
        self._styles: list[StyleEntry] = list(styles)
        self._renderers: dict[str, Renderer] = {}
        self._labelling: dict[str, Labelling] = {}

    def apply_style(self, layer_id: str, style: str) -> None:
        """Validate the target, then record the application."""
        self._scope.ensure_open()
        info = self._layers.layer(layer_id)
        spec = require_style(style)
        reasons = spec.incompatibilities(info)
        if reasons:
            raise QgisSdkStyleIncompatibleError(layer_id, style, reasons)
        self._applied.setdefault(layer_id, []).append(style)

    def applied(self, layer_id: str) -> tuple[str, ...]:
        """Return styles applied to a layer; observation, not part of the contract."""
        self._scope.ensure_open()
        self._layers.layer(layer_id)
        return tuple(self._applied.get(layer_id, ()))

    # -- symbology -----------------------------------------------------------

    def symbology(self, layer_id: str) -> Renderer:
        """Answer the renderer this backend holds for the layer."""
        info = self._vector(layer_id)
        stored = self._renderers.get(layer_id)
        if stored is not None:
            return stored
        return _default_renderer(info.geometry_type)

    def set_symbology(self, layer_id: str, renderer: Renderer) -> None:
        """Record a renderer, refusing a symbol its geometry cannot draw."""
        info = self._vector(layer_id)
        reason = symbol_fits_geometry(renderer, info.geometry_type)
        if reason is not None:
            raise QgisSdkStyleIncompatibleError(layer_id, renderer.kind, (reason,))
        self._renderers[layer_id] = renderer

    def labelling(self, layer_id: str) -> Labelling:
        """Answer the labelling this backend holds for the layer."""
        self._vector(layer_id)
        return self._labelling.get(layer_id, Labelling())

    def set_labelling(self, layer_id: str, labelling: Labelling) -> None:
        """Record a labelling."""
        self._vector(layer_id)
        self._labelling[layer_id] = labelling

    # -- the style manager and style text ------------------------------------

    def list_styles(self, kind: str | None = None) -> tuple[StyleEntry, ...]:
        """Answer the declared style entries, optionally of one kind."""
        self._scope.ensure_open()
        if kind is not None and kind not in STYLE_MANAGER_KINDS:
            raise ValueError(
                f"a style manager kind is one of {', '.join(STYLE_MANAGER_KINDS)}, "
                f"not {kind!r}"
            )
        return tuple(
            entry for entry in self._styles if kind is None or entry.kind == kind
        )

    def export_style(self, layer_id: str, format: str) -> StyleText:
        """Write the layer's renderer and labelling as this fake's document."""
        self._vector(layer_id)
        document = {
            "qgis_sdk_style": 1,
            "format": format,
            "renderer": self.symbology(layer_id).to_wire(),
            "labelling": self.labelling(layer_id).to_wire(),
        }
        return StyleText(format=format, text=json.dumps(document, sort_keys=True))

    def import_style(self, layer_id: str, text: str, format: str) -> None:
        """Read this fake's document back, refusing anything else."""
        info = self._vector(layer_id)
        try:
            document = json.loads(text)
        except ValueError as error:
            raise QgisSdkStyleTextError(format, str(error)) from None
        if not isinstance(document, dict) or document.get("qgis_sdk_style") != 1:
            raise QgisSdkStyleTextError(format, "not a style document this fake wrote")
        if document.get("format") != format:
            raise QgisSdkStyleTextError(
                format, f"the document is {document.get('format')!r}, not {format!r}"
            )
        renderer = renderer_from_wire(document["renderer"])
        reason = symbol_fits_geometry(renderer, info.geometry_type)
        if reason is not None:
            raise QgisSdkStyleIncompatibleError(layer_id, format, (reason,))
        self._renderers[layer_id] = renderer
        self._labelling[layer_id] = Labelling.from_wire(document["labelling"])

    def _vector(self, layer_id: str) -> VectorLayerInfo:
        """Return the layer, refusing one no renderer applies to."""
        self._scope.ensure_open()
        info = self._layers.layer(layer_id)
        if not isinstance(info, VectorLayerInfo):
            raise QgisSdkUnsupportedCapabilityError(
                info.id,
                f"a {info.kind} is drawn by QGIS, not by a renderer this SDK sets",
            )
        return info


def _default_renderer(geometry_type: str) -> Renderer:
    """The renderer a layer of ``geometry_type`` starts with, on either backend."""
    kind = SYMBOLS_FOR_GEOMETRY.get(geometry_type, "marker")
    color = "#808080"
    if kind == "line":
        return SingleSymbolRenderer(symbol=LineSymbol(color=color))
    if kind == "fill":
        return SingleSymbolRenderer(symbol=FillSymbol(color=color))
    return SingleSymbolRenderer(symbol=MarkerSymbol(color=color))


class RecordingNotifications(NotificationsBase):
    """A ``Notifications`` backend that records what it was given.

    ``messages`` is every message text in order, whatever its level - the
    assertion most tests want; ``records`` keeps the level and the button
    ``with_action`` attached, so a test can press it with :meth:`press`.
    """

    def __init__(self, scope: ResourceScope) -> None:
        self._scope = scope
        self.messages: list[str] = []
        self.records: list[Notification] = []
        self._dispatch: list[Callable[..., object] | None] = [None]

    def bind_actions(self, dispatch: Callable[..., object]) -> None:
        """Make :meth:`press` run ``dispatch(action_id, **arguments)``."""
        self._dispatch[0] = dispatch

    def press(self, index: int = -1) -> object:
        """Press the button of the ``index``-th record, as the user would."""
        record = self.records[index]
        if record.action is None:
            raise ValueError(f"notification {record.message!r} carries no action")
        dispatch = self._dispatch[0]
        if dispatch is None:
            raise ValueError(
                "no actions bound: call bind_actions(runtime.actions...) first"
            )
        return dispatch(record.action.action_id, **record.action.arguments)

    def _deliver(self, notification: Notification) -> None:
        self._scope.ensure_open()
        self.messages.append(notification.message)
        self.records.append(notification)


class RecordingLog(LogBase):
    """A ``Log`` backend that keeps every record it was given.

    ``records`` is the full :class:`LogRecord` list in order; ``messages``
    the message texts alone, whatever their level. ``plugin`` is the tag
    the records carry, ``"test"`` unless a test names its plugin.
    """

    def __init__(self, scope: ResourceScope, plugin: str = "test") -> None:
        super().__init__(plugin)
        self._scope = scope
        self.records: list[LogRecord] = []

    @property
    def messages(self) -> list[str]:
        """The message text of every record, in order."""
        return [record.message for record in self.records]

    def _deliver(self, record: LogRecord) -> None:
        self._scope.ensure_open()
        self.records.append(record)


class FakeProviderRegistration:
    """One provider a :class:`FakeProcessing` currently advertises."""

    def __init__(self, registry: FakeProcessing, provider: Provider) -> None:
        self._registry = registry
        self.provider = provider

    def unregister(self) -> None:
        """Take the provider down; a second call is a safe no-op."""
        self._registry._remove(self.provider.id, self)


class FakeProcessing:
    """A ``Processing`` registry that records what a host would advertise.

    It holds no toolbox, so it proves only the contract ``PluginRuntime``
    relies on: ``register_provider`` records the provider under its id,
    refuses a second registration of the same id by name - the way the QGIS
    registry refuses a duplicate provider - and ``unregister`` on the returned
    registration removes it again. ``registered`` is the ids currently held,
    in registration order; ``events`` is the full history a test can assert
    ordering against.
    """

    def __init__(self, scope: ResourceScope) -> None:
        self._scope = scope
        self._live: dict[str, FakeProviderRegistration] = {}
        self.events: list[tuple[str, str]] = []

    @property
    def registered(self) -> tuple[str, ...]:
        """The ids of the providers currently advertised."""
        return tuple(self._live)

    def provider(self, provider_id: str) -> Provider:
        """Return the provider advertised under ``provider_id``."""
        return self._live[provider_id].provider

    def register_provider(self, provider: Provider) -> FakeProviderRegistration:
        """Advertise ``provider``, refusing an id that is already live."""
        self._scope.ensure_open()
        if provider.id in self._live:
            raise QgisSdkDeclarationError(
                f"provider {provider.id!r} is already registered with the host"
            )
        registration = FakeProviderRegistration(self, provider)
        self._live[provider.id] = registration
        self.events.append(("register", provider.id))
        return registration

    def _remove(self, provider_id: str, registration: FakeProviderRegistration) -> None:
        if self._live.get(provider_id) is registration:
            del self._live[provider_id]
            self.events.append(("unregister", provider_id))


def table_entry(declaration: TableDeclaration) -> dict[str, object]:
    """The browse item and the vector shape one declared table answers."""
    return {
        "item": ConnectionItem(
            name=declaration.name,
            schema=declaration.schema,
            kind=declaration.kind,
            geometries=tuple(declaration.geometries),
        ),
        "fields": tuple(declaration.fields),
        "crs": declaration.crs,
    }


def refuse_unopenable(kind: str) -> None:
    if kind == "schema":
        raise QgisSdkUnsupportedCapabilityError(
            "connections.open_layer",
            "a schema is browsed, not opened",
        )
    if kind == "raster":
        raise QgisSdkUnsupportedCapabilityError(
            "connections.open_layer",
            "a raster table is opened by its raster provider, not "
            "described as a vector layer",
        )


def missing_table(connections, key, name, schema, item):
    schemas = connections._connections[key]["schemas"]
    if not schema and item in schemas:  # type: ignore[operator]
        raise QgisSdkUnsupportedCapabilityError(
            "connections.open_layer",
            "a schema is browsed, not opened",
        )
    raise QgisSdkConnectionItemNotFoundError(name, schema or "", item)
