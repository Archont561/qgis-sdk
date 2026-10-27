"""The declaration wire contract: its version, the stream event kinds, the error."""

from qgis_sdk.models import QgisSdkError

#: The event kinds a stream may declare and a frame may carry. This is the one
#: spelling: :mod:`qgis_sdk.bridge.protocol` validates frames against it and
#: ``qgis_sdk.bridge.streams.StreamEventType`` enumerates it, so a declaration
#: module never imports the bridge and the bridge never re-spells the kinds.
STREAM_EVENT_KINDS = ("data", "progress", "state")

#: Version of the plugin-description wire contract. It is deliberately not the
#: package version: the bridge mirrors this number, and a release that changes a
#: serialized shape has to move it for both sides at once.
PLUGIN_DESCRIPTION_SCHEMA_VERSION = 1


class QgisSdkDeclarationError(QgisSdkError):
    """A declaration cannot be represented in the versioned contract."""

    code = "invalid_declaration"
