"""QGIS-free networking: the injected client and typed clients composed over it.

The host supplies the transport (``qgis_sdk.adapters.qgis.NativeNetworkTransport``
in QGIS, ``qgis_sdk.testing.FakeNetworkTransport`` in tests); everything here
is importable and testable without Qt.
"""

from .client import BlockingNetworkClient, NetworkClient, NetworkDefaults, build_request
from .grants import NetworkGrant, origin_of
from .ogc import CollectionInfo, FeaturesPage, OgcApiFeatures

__all__ = [
    "BlockingNetworkClient",
    "CollectionInfo",
    "FeaturesPage",
    "NetworkClient",
    "NetworkDefaults",
    "NetworkGrant",
    "OgcApiFeatures",
    "build_request",
    "origin_of",
]
