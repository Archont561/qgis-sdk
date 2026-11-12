from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from qgis_sdk.adapters.palette import palette_theme
from qgis_sdk.bindings import (
    BoundSurface,
)
from qgis_sdk.core import PluginContext, PluginRuntime, UiServices
from qgis_sdk.models import QgisSdkError, QgisSdkUiError
from qgis_sdk.ui.actions import ViewActions
from qgis_sdk.ui.streams import ViewStreams
from qgis_sdk.ui.surfaces import Surface, describe_surface

from ._entries import OpenDialog, OpenDock, chosen_surfaces, dock_visible_setting

if TYPE_CHECKING:
    from qgis_sdk.adapters.snapshot import SurfaceCapture


class SurfaceHostMixin1:
    def attach(self, runtime: PluginRuntime, context: PluginContext) -> None:
        """Bind the started runtime and its context; ``host()`` does this once."""
        self._runtime = runtime
        self._context = context

    @property
    def dialogs(self) -> tuple[OpenDialog, ...]:
        """The dialogs currently open, oldest first."""
        return tuple(dialog for dialog in self._dialogs if not dialog.closed)

    @property
    def docks(self) -> Mapping[type, OpenDock]:
        """The dock instances built so far, by surface class."""
        return MappingProxyType(self._docks)

    # -- snapshots ----------------------------------------------------------------

    def snapshot(
        self, surface_id: str | None = None, *, screenshot: bool = True
    ) -> tuple[SurfaceCapture, ...]:
        """Capture the surfaces this plugin opened (decision-51).

        Only this host's own surfaces are visible: a dialog it showed or a
        dock it built and left visible. ``surface_id`` selects one and raises
        for an unknown id; by default every open surface is captured.
        """
        from qgis_sdk.adapters.snapshot import capture_surface

        chosen = chosen_surfaces(self._opened_surfaces(), surface_id)
        theme = palette_theme()
        palette = theme["palette"] if theme is not None else None
        return tuple(
            capture_surface(
                widget,
                surface_id=name,
                kind=kind,
                title=title,
                screenshot=screenshot,
                palette=palette,
            )
            for name, kind, title, widget in chosen
        )

    def _opened_surfaces(self) -> list[tuple[str, str, str, Any]]:
        entries: list[tuple[str, str, str, Any]] = []
        for dialog in self.dialogs:
            description = describe_surface(type(dialog.surface))
            entries.append(
                (description.id, description.kind, description.title, dialog.widget)
            )
        for dock in self.docks.values():
            visible = getattr(dock.widget, "isVisible", None)
            if not callable(visible) or not visible():
                continue
            description = describe_surface(type(dock.surface))
            entries.append(
                (description.id, description.kind, description.title, dock.widget)
            )
        return entries

    # -- ctx.ui --------------------------------------------------------------------

    def open(
        self, surface: type, *, initial: Mapping[str, object] | None = None
    ) -> Surface:
        """Show ``surface``: a new dialog, or the one dock made visible."""
        _runtime, context = self._require_attached()
        context.scope.ensure_open()
        bound = self._registered(surface)
        if bound.surface.kind == "dock":
            dock = self._ensure_dock(bound, initial)
            dock.widget.show()
            dock.widget.raise_()
            return dock.surface
        return self._open_dialog(bound, initial).surface

    def toggle(self, surface: type, visible: bool) -> None:
        """Show or hide a dock from its checkable binding."""
        bound = self._registered(surface)
        if visible:
            self._ensure_dock(bound, None).widget.show()
        elif surface in self._docks:
            self._docks[surface].widget.hide()

    def restore_docks(self) -> None:
        """Open the docks the last session left visible (``ctx.settings``)."""
        settings = self._settings()
        if settings is None:
            return
        for bound in self._bindings.surfaces:
            if bound.surface.kind != "dock":
                continue
            if settings.get(dock_visible_setting(bound.id)) == "true":
                self._ensure_dock(bound, None).widget.show()

    def close_all(self) -> None:
        """Close every dialog and remove every dock; safe to repeat.

        Unload is not the user hiding a panel, so a dock's remembered
        visibility is left as it was while the plugin ran.
        """
        self._closing = True
        for dialog in list(self._dialogs):
            if not dialog.closed:
                dialog.widget.close()
            self._dispose_dialog(dialog)
        self._dialogs.clear()
        for surface, dock in list(self._docks.items()):
            if self._iface is not None:
                self._iface.removeDockWidget(dock.widget)
            self._dispose(dock.surface, dock.scope)
            dock.widget.deleteLater()
            del self._docks[surface]
        self._runtime = None
        self._context = None
        self._closing = False

    # -- the pieces ------------------------------------------------------------------

    def _require_attached(self) -> tuple[PluginRuntime, PluginContext]:
        if self._runtime is None or self._context is None:
            raise QgisSdkUiError(
                f"{self._title}: surfaces open only while the plugin runs"
            )
        return self._runtime, self._context

    def _registered(self, surface: type) -> BoundSurface:
        try:
            return self._bindings.surface(surface)
        except QgisSdkError as error:
            raise QgisSdkUiError(str(error)) from error

    def _settings(self) -> Any | None:
        context = self._context
        if context is None or not context.has("settings"):
            return None
        return context.settings

    def _view_services(
        self,
        context: PluginContext,
        scope: Any,
        actions: ViewActions,
        streams: ViewStreams,
    ) -> UiServices:
        """What a view's context offers: its own actions and streams, and the rest."""
        return UiServices(
            host=context.host,
            network=context.network if context.has("network") else None,
            actions=actions,
            settings=self._settings(),
            layers=context.layers if context.has("layers") else None,
            project=context.project if context.has("project") else None,
            files=context.files if context.has("files") else None,
            log=context.log if context.has("log") else None,
            streams=streams,
            algorithms=context.algorithms if context.has("algorithms") else None,
            styles=context.styles if context.has("styles") else None,
            desktop=context.desktop if context.has("desktop") else None,
            ui=context.ui if context.has("ui") else None,
            jobs=context.jobs.scoped(scope) if context.has("jobs") else None,
        )
