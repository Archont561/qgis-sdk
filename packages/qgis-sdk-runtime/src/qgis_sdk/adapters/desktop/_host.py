from __future__ import annotations

import functools
import importlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qgis_sdk.bindings import BindingsDescription, describe_bindings
from qgis_sdk.core import (
    PluginContext,
    PluginRuntime,
)
from qgis_sdk.core._application import QgisSdkPlugin
from qgis_sdk.models import QgisSdkError

from ._lifecycle import (
    ASSETS_DIRECTORY,
    CONTEXT_FACTORY_ATTRIBUTE,
    PLACEMENTS,
    ContextFactory,
    DesktopHostOptions,
    DesktopLifecycleAdapter,
    QgisSdkHostError,
    default_context,
    desktop_surfaces,
    resolve_plugin_spec,
)

if TYPE_CHECKING:
    from qgis_sdk.adapters.surfaces._bindings import DesktopBindings
    from qgis_sdk.adapters.surfaces._host import SurfaceHost


class DesktopHost:
    """What ``host()``'s ``classFactory`` hands QGIS: lifecycle, bindings, page.

    Beside the page (decision-43) it places the plugin's Desktop bindings
    (decision-45/55): the ``@toolbar``/``@menu``/``@shortcut`` entries of
    its actions and of its ``Dialog``/``Dock`` surfaces, created on
    ``initGui`` after the runtime starts and removed on ``unload`` before it
    stops. Inside a running QGIS the context also gains ``ctx.ui``, the way
    an action opens a registered surface; in a bare interpreter it does not,
    and ``ctx.ui`` is refused by name.
    """

    def __init__(
        self,
        app: QgisSdkPlugin,
        iface: object | None,
        options: DesktopHostOptions,
    ) -> None:
        self._iface = iface
        self._title = options.title
        self._view_id = options.view_id
        self._placement = options.placement
        self._grants = options.grants
        self._assets = options.assets
        self._package_directory = options.package_directory or options.assets.parent
        self._options = options
        self._action: Any | None = None
        self._view: Any | None = None
        self._bindings = (
            options.bindings if options.bindings is not None else describe_bindings(app)
        )
        self._surfaces, self._desktop_bindings = desktop_surfaces(
            iface, self._bindings, options.title, self._package_directory
        )
        factory = options.context_factory
        if self._surfaces is not None:
            factory = _with_ui(factory, self._surfaces)
        self._adapter = DesktopLifecycleAdapter(app, iface, context_factory=factory)

    @property
    def iface(self) -> object | None:
        return self._iface

    @property
    def runtime(self) -> PluginRuntime:
        """The SDK runtime: tests read it, the page's dispatcher is built from it."""
        return self._adapter.runtime

    @property
    def context(self) -> PluginContext:
        return self._adapter.context

    def console(self) -> Any:
        """Return a console session bound to this plugin's context (decision-48)."""
        return self._adapter.console()

    @property
    def placement(self) -> str | None:
        """Where the page shows, or ``None`` for a plugin without one."""
        return self._placement

    @property
    def grants(self) -> tuple[str, ...]:
        """The curated host operations the page may call."""
        return self._grants

    @property
    def view(self) -> Any | None:
        """The dock or dialog while the page is open, else ``None``."""
        return self._view

    @property
    def bindings(self) -> BindingsDescription:
        """The bound actions and registered surfaces ``host()`` read."""
        return self._bindings

    @property
    def surfaces(self) -> SurfaceHost | None:
        """The surface host (``ctx.ui``) inside QGIS, else ``None``."""
        return self._surfaces

    @property
    def desktop_bindings(self) -> DesktopBindings | None:
        """The placed toolbar/menu/shortcut actions inside QGIS, else ``None``."""
        return self._desktop_bindings

    def initGui(self) -> None:
        """Start the plugin, place its bindings; with a page, add its button."""
        self._adapter.initGui()
        _bind_notification_actions(self.context, self.runtime)
        if self._surfaces is not None and self._desktop_bindings is not None:
            self._surfaces.attach(self.runtime, self.context)
            self._desktop_bindings.install(self.runtime)
            self._surfaces.restore_docks()
            self._desktop_bindings.sync_toggles()
        if self._placement is not None:
            from qgis_sdk.adapters.webview import add_toolbar_action

            self._action = add_toolbar_action(self._iface, self._title, self.show_view)

    def show_view(self) -> Any:
        """Open the page on first use; bring it to the front after that."""
        if self._placement is None:
            raise QgisSdkHostError(
                f"{self._title} declares no page; add [tool.qgis-sdk.web] to show one"
            )
        if self._view is None:
            from qgis_sdk.adapters.webview import open_view

            self._view = open_view(
                self.runtime,
                self.context,
                self._iface,
                title=self._title,
                view_id=self._view_id,
                placement=self._placement,
                assets=self._assets,
                grants=self._grants,
            )
        self._view.show()
        self._view.raise_()
        return self._view

    def unload(self) -> None:
        """Close the page and surfaces, remove every button, stop the plugin."""
        if self._desktop_bindings is not None:
            self._desktop_bindings.remove()
        if self._surfaces is not None:
            self._surfaces.close_all()
        if self._view is not None:
            from qgis_sdk.adapters.webview import close_view

            close_view(self._view, self._iface)
            self._view = None
        if self._action is not None:
            from qgis_sdk.adapters.webview import remove_toolbar_action

            remove_toolbar_action(self._iface, self._action)
            self._action = None
        _bind_notification_actions(self.context, None)
        self._adapter.unload()


def _bind_notification_actions(
    context: PluginContext, runtime: PluginRuntime | None
) -> None:
    """Route ``with_action`` buttons to the running plugin's handlers, or nowhere."""
    bind = getattr(context.notifications, "bind_actions", None)
    if bind is None:
        return
    if runtime is None:
        bind(None)
        return

    def dispatch(action_id: str, **arguments: Any) -> object:
        return runtime.actions[action_id](**arguments)

    bind(dispatch)


def _with_ui(factory: ContextFactory, surfaces: SurfaceHost) -> ContextFactory:
    """Wrap ``factory`` so the context gains ``ui`` unless the author set one."""

    def with_ui(iface: object | None) -> PluginContext:
        context = factory(iface)
        if context.has("ui"):
            return context
        return context.with_services(ui=surfaces)

    return with_ui


def _host_grants(grants: Sequence[str], placement: str | None) -> tuple[str, ...]:
    """Resolve the declared grants; a page is required when any are given."""
    if not grants:
        return ()
    from qgis_sdk.bridge.host import granted_operations

    try:
        granted = granted_operations(tuple(grants))
    except QgisSdkError as error:
        raise QgisSdkHostError(str(error)) from error
    if granted and placement is None:
        raise QgisSdkHostError("grants need a page; set placement as well")
    return granted


def _host_context_factory(app: QgisSdkPlugin, description: Any) -> ContextFactory:
    """Use the application's own factory, else the default context factory."""
    factory: ContextFactory | None = getattr(app, CONTEXT_FACTORY_ATTRIBUTE, None)
    if factory is None:
        factory = functools.partial(
            default_context, plugin_id=description.id, title=description.title
        )
    return factory


def _validate_placement(placement: str | None) -> None:
    if placement is not None and placement not in PLACEMENTS:
        raise QgisSdkHostError(
            f"placement must be one of {', '.join(PLACEMENTS)}, got {placement!r}"
        )


def _host_application(
    spec: str, placement: str | None, grants: Sequence[str]
) -> tuple[QgisSdkPlugin, DesktopHostOptions]:
    """Resolve the application and build the one record its host needs."""
    _validate_placement(placement)
    granted = _host_grants(grants, placement)
    app = resolve_plugin_spec(spec)
    description = app.describe()
    package_directory = _package_directory(spec.partition(":")[0])
    options = DesktopHostOptions(
        context_factory=_host_context_factory(app, description),
        title=description.title,
        view_id=f"{description.id}.main",
        placement=placement,
        grants=granted,
        assets=package_directory / ASSETS_DIRECTORY,
        bindings=description.bindings,
        package_directory=package_directory,
    )
    return app, options


def host(
    spec: str,
    *,
    placement: str | None = None,
    grants: Sequence[str] = (),
) -> Callable[[object | None], DesktopHost]:
    """Return the ``classFactory`` for the application ``spec`` names.

    ``build``/``dev`` write the one line that calls this; an author never does.
    ``placement`` (``dock``/``dialog``) turns the page on; ``grants`` names the
    curated host operations the page may call, none by default. An application's
    ``context_factory`` replaces :func:`default_context`.
    """
    app, options = _host_application(spec, placement, grants)

    def classFactory(iface: object | None) -> DesktopHost:
        return DesktopHost(app, iface, options)

    return classFactory


def _package_directory(module_name: str) -> Path:
    """The top-level package directory the application's module lives under.

    Read from the module's file, not the package's ``__file__``: under
    ``qgis-sdk dev`` the package's ``__init__`` is the generated host module
    in ``.qgis-sdk/dev/host`` while the sources - and ``web/`` - stay put.
    """
    module = importlib.import_module(module_name)
    file = getattr(module, "__file__", None)
    if file is None:
        raise QgisSdkHostError(f"{module_name} has no file to locate web/")
    depth = module_name.count(".")
    path = Path(file).resolve()
    return path.parents[max(depth - 1, 0)] if depth else path.parent
