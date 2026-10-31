"""Test doubles for the curated service contracts.

Production modules must not import this package: the import-boundary test in
``tests/test_pure_imports.py`` treats it as the outermost pure layer precisely so
that a fake can never become a runtime fallback. The fakes ship with the runtime
because they implement its service protocols and must version with them
(decision-35); ``FakeCliRuntime`` fakes a tools type and lives in
``qgis_sdk_tools.testing``.
"""

from .app import FakeAppBackend, FakeAppSurface, FakeLoop
from .fakes import (
    FakeAlgorithms,
    FakeLayers,
    FakeProcessing,
    FakeProject,
    FakeSettings,
    FakeStyles,
    RecordingLog,
    RecordingNotifications,
)
from .features import FakeEditingSession, FakeFeatures, FakeLayer
from .files import FakeFiles
from .jobs import FakeWorkers, ThreadWorkers
from .network import (
    FakeNetworkTransport,
    PendingRequest,
    QgisSdkNetworkFakeError,
    reply,
)
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
    "BuiltSurface",
    "FakeAlgorithms",
    "FakeAppBackend",
    "FakeAppSurface",
    "FakeEditingSession",
    "FakeFeatures",
    "FakeFiles",
    "FakeLayer",
    "FakeLayers",
    "FakeLoop",
    "FakeNetworkTransport",
    "FakeProcessing",
    "FakeProject",
    "FakeServerInterface",
    "FakeSettings",
    "FakeStyles",
    "FakeUi",
    "FakeViewControl",
    "FakeWorkers",
    "OpenedSurface",
    "PendingRequest",
    "QgisSdkNetworkFakeError",
    "RecordingLog",
    "RecordingNotifications",
    "RegisteredFilter",
    "ThreadWorkers",
    "build_surface",
    "fake_ui_context",
    "reply",
]
