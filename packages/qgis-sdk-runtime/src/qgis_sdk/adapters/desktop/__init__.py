"""Module desktop."""

from __future__ import annotations

from ._host import (
    DesktopHost,
    host,
)
from ._lifecycle import (
    CONTEXT_FACTORY_ATTRIBUTE,
    ContextFactory,
    DesktopHostOptions,
    DesktopLifecycleAdapter,
    MessageBarNotifications,
    QgisSdkHostError,
    create_class_factory,
    default_context,
    qgis_is_running,
    resolve_plugin_spec,
)

__all__ = [
    "CONTEXT_FACTORY_ATTRIBUTE",
    "ContextFactory",
    "DesktopHost",
    "DesktopHostOptions",
    "DesktopLifecycleAdapter",
    "MessageBarNotifications",
    "QgisSdkHostError",
    "create_class_factory",
    "default_context",
    "host",
    "qgis_is_running",
    "resolve_plugin_spec",
]
