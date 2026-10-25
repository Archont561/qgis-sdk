"""Test doubles for the curated service contracts.

Production modules must not import this package: the import-boundary test in
``tests/test_pure_imports.py`` treats it as the outermost pure layer precisely so
that a fake can never become a runtime fallback.
"""

from .cli import FakeCliRuntime, FakeProcess
from .fakes import (
    FakeAlgorithms,
    FakeLayers,
    FakeProject,
    FakeSettings,
    FakeStyles,
    RecordingNotifications,
)
from .jobs import FakeWorkers
from .network import (
    FakeNetworkTransport,
    PendingRequest,
    QgisSdkNetworkFakeError,
    reply,
)

__all__ = [
    "FakeAlgorithms",
    "FakeCliRuntime",
    "FakeLayers",
    "FakeNetworkTransport",
    "FakeProcess",
    "FakeProject",
    "FakeSettings",
    "FakeStyles",
    "FakeWorkers",
    "PendingRequest",
    "QgisSdkNetworkFakeError",
    "RecordingNotifications",
    "reply",
]
