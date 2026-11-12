"""The declared operation table, the grants that select from it and the description."""

from __future__ import annotations

from qgis_sdk.bridge.host._schemas import (
    _NOTHING,
    GUI,
    LAYER_INFO,
    PAGE_REQUEST,
    VECTOR_LAYER_INFO,
    object,
    page_result,
)
from qgis_sdk.models.connections import (
    CONNECTION_INFO,
    CONNECTION_ITEM,
)
from qgis_sdk.models.symbology import (
    LABELLING,
    RENDERER,
    STYLE_FORMATS,
    STYLE_MANAGER_KINDS,
    STYLE_TEXT,
)

from ._operation import (
    STYLE_ENTRIES,
    HostOperation,
)

HOST_OPERATIONS_A = (
    HostOperation(
        id="layers.list",
        title="List the layers this runtime opened",
        source="Layers.list_layers",
        grant="layers.read",
        affinity=GUI,
        request=PAGE_REQUEST,
        result=page_result(LAYER_INFO),
        request_name="PageRequest",
        result_name="LayerPage",
    ),
    HostOperation(
        id="layers.get",
        title="Describe one opened layer",
        source="Layers.layer",
        grant="layers.read",
        affinity=GUI,
        request=object({"layer_id": {"type": "string"}}, required=("layer_id",)),
        result=LAYER_INFO,
        request_name="LayerRequest",
        result_name="LayerInfo",
    ),
    HostOperation(
        id="project.layer_ids",
        title="List the project's layer ids in project order",
        source="Project.layer_ids",
        grant="project.read",
        affinity=GUI,
        request=PAGE_REQUEST,
        result=page_result({"type": "string"}),
        result_name="IdPage",
    ),
    HostOperation(
        id="settings.get",
        title="Read one setting owned by this runtime",
        source="Settings.get",
        grant="settings.read",
        affinity=GUI,
        request=object(
            {
                "key": {"type": "string"},
                "default": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            },
            required=("key",),
        ),
        result={"anyOf": [{"type": "string"}, {"type": "null"}]},
    ),
    HostOperation(
        id="notifications.info",
        title="Publish an informational message",
        source="Notifications.info",
        grant="notifications.info",
        affinity=GUI,
        request=object({"message": {"type": "string"}}, required=("message",)),
        result=_NOTHING,
    ),
    HostOperation(
        id="styles.apply",
        title="Apply one packaged style to an owned layer",
        source="Styles.apply_style",
        grant="styles.apply",
        affinity=GUI,
        request=object(
            {"layer_id": {"type": "string"}, "style": {"type": "string"}},
            required=("layer_id", "style"),
        ),
        result=_NOTHING,
        # Applying a style replaces the layer's whole symbology: an agent that
        # could do it silently would change how a map is drawn without consent.
        destructive=True,
    ),
    HostOperation(
        id="symbology.get",
        title="Describe the renderer drawing a layer",
        source="Styles.symbology",
        grant="symbology.read",
        affinity=GUI,
        request=object({"layer_id": {"type": "string"}}, required=("layer_id",)),
        result=RENDERER,
        request_name="SymbologyRequest",
        result_name="Renderer",
    ),
    HostOperation(
        id="symbology.set",
        title="Draw a layer with a described renderer",
        source="Styles.set_symbology",
        grant="symbology.write",
        affinity=GUI,
        request=object(
            {"layer_id": {"type": "string"}, "renderer": RENDERER},
            required=("layer_id", "renderer"),
        ),
        result=_NOTHING,
        request_name="SetSymbologyRequest",
        destructive=True,
    ),
    HostOperation(
        id="labelling.get",
        title="Describe how a layer's features are labelled",
        source="Styles.labelling",
        grant="symbology.read",
        affinity=GUI,
        request=object({"layer_id": {"type": "string"}}, required=("layer_id",)),
        result=LABELLING,
        request_name="LabellingRequest",
        result_name="Labelling",
    ),
    HostOperation(
        id="labelling.set",
        title="Label a layer's features, or switch labelling off",
        source="Styles.set_labelling",
        grant="symbology.write",
        affinity=GUI,
        request=object(
            {"layer_id": {"type": "string"}, "labelling": LABELLING},
            required=("layer_id", "labelling"),
        ),
        result=_NOTHING,
        request_name="SetLabellingRequest",
        destructive=True,
    ),
    HostOperation(
        id="styles.list",
        title="List what the QGIS style manager offers",
        source="Styles.list_styles",
        grant="styles.read",
        affinity=GUI,
        request=object({"kind": {"enum": list(STYLE_MANAGER_KINDS)}}),
        result=STYLE_ENTRIES,
        request_name="StyleListRequest",
        result_name="StyleEntries",
    ),
    HostOperation(
        id="styles.export",
        title="Export a layer's style as QML or SLD text",
        source="Styles.export_style",
        grant="styles.read",
        affinity=GUI,
        request=object(
            {
                "layer_id": {"type": "string"},
                "format": {"enum": list(STYLE_FORMATS)},
            },
            required=("layer_id", "format"),
        ),
        result=STYLE_TEXT,
        request_name="ExportStyleRequest",
        result_name="StyleText",
    ),
    HostOperation(
        id="styles.import",
        title="Apply QML or SLD text to a layer",
        source="Styles.import_style",
        grant="styles.write",
        affinity=GUI,
        request=object(
            {
                "layer_id": {"type": "string"},
                "format": {"enum": list(STYLE_FORMATS)},
                "text": {"type": "string"},
            },
            required=("layer_id", "format", "text"),
        ),
        result=_NOTHING,
        request_name="ImportStyleRequest",
        destructive=True,
    ),
    HostOperation(
        id="connections.list",
        title="List the registered data-source connections",
        source="Connections.list_connections",
        grant="connections.read",
        affinity=GUI,
        request=PAGE_REQUEST,
        result=page_result(CONNECTION_INFO),
        request_name="PageRequest",
        result_name="ConnectionPage",
    ),
    HostOperation(
        id="connections.describe",
        title="Describe one registered connection",
        source="Connections.connection",
        grant="connections.read",
        affinity=GUI,
        request=object(
            {
                "provider": {"type": "string"},
                "connection": {"type": "string"},
            },
            required=("provider", "connection"),
        ),
        result=CONNECTION_INFO,
        request_name="ConnectionRequest",
        result_name="ConnectionInfo",
    ),
    HostOperation(
        id="connections.browse",
        title="Browse the schemas or the tables one connection holds",
        source="Connections.browse",
        grant="connections.read",
        affinity=GUI,
        request=object(
            {
                "provider": {"type": "string"},
                "connection": {"type": "string"},
                "schema": {"type": "string"},
            },
            required=("provider", "connection"),
        ),
        result=page_result(CONNECTION_ITEM),
        request_name="ConnectionBrowseRequest",
        result_name="ConnectionItemPage",
        # A browse queries the database with the authentication the connection
        # stores; a page cannot walk a server's catalog without spending it.
        credential=True,
    ),
    HostOperation(
        id="connections.open_layer",
        title="Open one table of a connection as a vector layer",
        source="Connections.open_layer",
        grant="layers.open",
        affinity=GUI,
        request=object(
            {
                "provider": {"type": "string"},
                "connection": {"type": "string"},
                "schema": {"type": "string"},
                "item": {"type": "string"},
            },
            required=("provider", "connection", "schema", "item"),
        ),
        result=VECTOR_LAYER_INFO,
        request_name="ConnectionItemRequest",
        result_name="VectorLayerInfo",
        # Opening the table authenticates exactly as browsing it does.
        credential=True,
    ),
)
