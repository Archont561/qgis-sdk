"""Fakes for the UI contracts: a recording ``Ui`` and a recording ``ViewControl``.

``FakeUi`` is what a pure test hands a ``PluginContext`` as ``ui``: an action
that calls ``self.ctx.ui.open(BufferDialog, initial={...})`` is observed as
one :class:`OpenedSurface` record, and nothing is built - ``build()`` is the
author's Qt code and runs only under a host. Given the plugin class, the fake
also refuses a surface the class does not list, exactly as the Desktop does.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui.surfaces import describe_surface, is_surface_class

__all__ = ["FakeUi", "FakeViewControl", "OpenedSurface"]


@dataclass(frozen=True, slots=True)
class OpenedSurface:
    """One ``ctx.ui.open`` call the fake recorded."""

    surface: type
    initial: Mapping[str, object]

    @property
    def id(self) -> str:
        return describe_surface(self.surface).id


class FakeUi:
    """Record ``open`` calls; refuse unregistered surfaces when a plugin is known."""

    def __init__(
        self, scope: ResourceScope, *, plugin_class: type | None = None
    ) -> None:
        self._scope = scope
        self._plugin_class = plugin_class
        self._opened: list[OpenedSurface] = []

    @property
    def opened(self) -> tuple[OpenedSurface, ...]:
        """Every recorded opening, oldest first."""
        return tuple(self._opened)

    def open(
        self, surface: type, *, initial: Mapping[str, object] | None = None
    ) -> OpenedSurface:
        self._scope.ensure_open()
        if not is_surface_class(surface):
            name = getattr(surface, "__name__", repr(surface))
            raise QgisSdkUiError(f"{name} is not a Dialog/Dock subclass")
        if self._plugin_class is not None:
            from qgis_sdk.bindings import describe_bindings

            if all(
                bound.cls is not surface
                for bound in describe_bindings(self._plugin_class).surfaces
            ):
                raise QgisSdkUiError(
                    f"{surface.__name__} is not registered: list it in "
                    f"{self._plugin_class.__name__}.surfaces"
                )
        record = OpenedSurface(surface, MappingProxyType(dict(initial or {})))
        self._opened.append(record)
        return record


@dataclass(slots=True)
class FakeViewControl:
    """Count close requests; the owning test decides what closing means."""

    close_requests: int = field(default=0)

    def request_close(self) -> None:
        self.close_requests += 1
