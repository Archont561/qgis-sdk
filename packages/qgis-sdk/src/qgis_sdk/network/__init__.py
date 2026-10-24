"""QGIS-free networking: the injected client and typed clients composed over it.

The host supplies the transport (``qgis_sdk.adapters.qgis.NativeNetworkTransport``
in QGIS, ``qgis_sdk.testing.FakeNetworkTransport`` in tests); everything here
is importable and testable without Qt.
"""

from .client import BlockingNetworkClient, NetworkClient, NetworkDefaults, build_request
from .ogc import CollectionInfo, FeaturesPage, OgcApiFeatures

__all__ = [
    "BlockingNetworkClient",
    "CollectionInfo",
    "FeaturesPage",
    "NetworkClient",
    "NetworkDefaults",
    "OgcApiFeatures",
    "build_request",
]
