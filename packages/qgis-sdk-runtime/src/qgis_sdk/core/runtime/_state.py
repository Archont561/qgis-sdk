"""Lifecycle state and the error a refused start raises."""

from __future__ import annotations

from enum import StrEnum

from qgis_sdk.models import QgisSdkError

__all__ = ["PluginRuntimeState", "QgisSdkPluginLifecycleError"]


class QgisSdkPluginLifecycleError(QgisSdkError):
    """The runtime refused a start, unload or action binding."""

    code = "invalid_plugin_lifecycle"


class PluginRuntimeState(StrEnum):
    """Observable lifecycle state of one plugin runtime."""

    NEW = "new"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
