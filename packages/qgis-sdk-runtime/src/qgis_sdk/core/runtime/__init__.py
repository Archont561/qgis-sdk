"""Lifecycle ownership for one application and its runtime scope."""

from __future__ import annotations

from ._providers import declared_providers as _declared_providers  # noqa: F401
from ._providers import job_registry as _job_registry  # noqa: F401
from ._runtime import PluginRuntime
from ._state import PluginRuntimeState, QgisSdkPluginLifecycleError

__all__ = ["PluginRuntime", "PluginRuntimeState", "QgisSdkPluginLifecycleError"]
