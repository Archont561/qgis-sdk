"""Test doubles for the curated service contracts.

Production modules must not import this package: the import-boundary test in
``tests/test_pure_imports.py`` treats it as the outermost pure layer precisely so
that a fake can never become a runtime fallback.
"""

from .fakes import (
    FakeLayers,
    FakeProject,
    FakeSettings,
    FakeStyles,
    RecordingNotifications,
)

__all__ = [
    "FakeLayers",
    "FakeProject",
    "FakeSettings",
    "FakeStyles",
    "RecordingNotifications",
]
