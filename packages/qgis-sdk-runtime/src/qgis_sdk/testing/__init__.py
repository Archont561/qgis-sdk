"""Test doubles for the curated service contracts.

Production modules must not import this package: the import-boundary test in
``tests/test_pure_imports.py`` treats it as the outermost pure layer precisely so
that a fake can never become a runtime fallback. The fakes ship with the runtime
because they implement its service protocols and must version with them
(decision-35); ``FakeCliRuntime`` fakes a tools type and lives in
``qgis_sdk_tools.testing``.
"""

from .app import FakeAppBackend, FakeAppSurface, FakeLoop
from .canvas import DEFAULT_EXTENT, FakeCanvas
from .fakes import (
    ConnectionDeclaration,
    DeclaredOutput,
    FakeAlgorithms,
    FakeAlgorithmSetup,
    FakeConnections,
    FakeLayers,
    FakeProcessing,
    FakeSettings,
    FakeStyles,
    OtherLayerDeclaration,
    RecordingLog,
    RecordingNotifications,
    TableDeclaration,
    VectorLayerDeclaration,
)
from .features import FakeEditingSession, FakeFeatures, FakeLayer
from .files import FakeFiles
from .jobs import FakeWorkers, ThreadWorkers
from .layouts import FakeLayouts
from .network import (
    FakeNetworkTransport,
    PendingRequest,
    QgisSdkNetworkFakeError,
    reply,
)
from .project import FakeProject
from .rasters import FakeRasters
from .server import FakeServerInterface, RegisteredFilter
from .ui import (
    BuiltSurface,
    FakeUi,
    FakeViewControl,
    OpenedSurface,
    build_surface,
    fake_ui_context,
)

__all__ = [
    "DEFAULT_EXTENT",
    "BuiltSurface",
    "ConnectionDeclaration",
    "DeclaredOutput",
    "FakeAlgorithmSetup",
    "FakeAlgorithms",
    "FakeAppBackend",
    "FakeAppSurface",
    "FakeCanvas",
    "FakeConnections",
    "FakeEditingSession",
    "FakeFeatures",
    "FakeFiles",
    "FakeLayer",
    "FakeLayers",
    "FakeLayouts",
    "FakeLoop",
    "FakeNetworkTransport",
    "FakeProcessing",
    "FakeProject",
    "FakeRasters",
    "FakeServerInterface",
    "FakeSettings",
    "FakeStyles",
    "FakeUi",
    "FakeViewControl",
    "FakeWorkers",
    "OpenedSurface",
    "OtherLayerDeclaration",
    "PendingRequest",
    "QgisSdkNetworkFakeError",
    "RecordingLog",
    "RecordingNotifications",
    "RegisteredFilter",
    "TableDeclaration",
    "ThreadWorkers",
    "VectorLayerDeclaration",
    "build_surface",
    "fake_ui_context",
    "reply",
]
