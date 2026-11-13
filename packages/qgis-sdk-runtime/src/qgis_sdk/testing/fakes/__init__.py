"""Module fakes."""

from __future__ import annotations

from ._algorithms import (
    FakeAlgorithms,
)
from ._connections import FakeConnections
from ._declarations import (
    ConnectionDeclaration,
    DeclaredOutput,
    FakeAlgorithmSetup,
    FakeProject,
    OtherLayerDeclaration,
    TableDeclaration,
    VectorLayerDeclaration,
)
from ._layers import (
    FakeLayers,
    FakeSettings,
)
from ._styles import (
    FakeProcessing,
    FakeProviderRegistration,
    FakeStyles,
    RecordingLog,
    RecordingNotifications,
)

__all__ = [
    "ConnectionDeclaration",
    "DeclaredOutput",
    "FakeAlgorithmSetup",
    "FakeAlgorithms",
    "FakeConnections",
    "FakeLayers",
    "FakeProcessing",
    "FakeProject",
    "FakeProviderRegistration",
    "FakeSettings",
    "FakeStyles",
    "OtherLayerDeclaration",
    "RecordingLog",
    "RecordingNotifications",
    "TableDeclaration",
    "VectorLayerDeclaration",
]
