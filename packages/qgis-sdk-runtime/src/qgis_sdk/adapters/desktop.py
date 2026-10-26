"""Desktop lifecycle glue for QGIS ``classFactory``/``initGui``/``unload``.

Two layers. :class:`DesktopLifecycleAdapter` and :func:`create_class_factory`
delegate construction and disposal to :class:`PluginRuntime` and know nothing
about QGIS: the host passes ``iface`` and a ``context_factory`` supplies the
typed capabilities. :func:`host` is what a generated plugin binds
(decision-43): ``classFactory = host("pkg.plugin:Class")`` resolves the
author's class, builds the context the running host can offer - every
curated service inside QGIS, a bare context that refuses ``ctx.desktop`` by
name anywhere else - and, when the project declares a page, owns the toolbar
button and the page view. Nothing here imports QGIS or Qt at module level,
so the pure starter tests call ``classFactory(None)`` without a display.
"""

from __future__ import annotations

import functools
import importlib
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from qgis_sdk.bindings import BindingsDescription, describe_bindings
from qgis_sdk.core import PluginContext, PluginFactory, PluginRuntime, ResourceScope
from qgis_sdk.declarations import describe_plugin
from qgis_sdk.models import QgisSdkError

if TYPE_CHECKING:
    from qgis_sdk.adapters.surfaces import DesktopBindings, SurfaceHost

__all__ = [
    "CONTEXT_FACTORY_ATTRIBUTE",
    "ContextFactory",
    "DesktopHost",
    "DesktopLifecycleAdapter",
    "MessageBarNotifications",
    "QgisSdkHostError",
    "create_class_factory",
    "default_context",
    "host",
    "qgis_is_running",
    "resolve_plugin_spec",
]

ContextFactory = Callable[[object], PluginContext]
"""Build the plugin context from the host's opaque Desktop ``iface``."""

#: A plugin class may bind this to a callable ``(iface) -> PluginContext`` to
#: replace :func:`default_context`; the only hook :func:`host` offers.
CONTEXT_FACTORY_ATTRIBUTE: Final = "context_factory"
#: The directory, inside the plugin package, a built page lives in.
ASSETS_DIRECTORY: Final = "web"
PLACEMENTS: Final = ("dock", "dialog")


class QgisSdkHostError(QgisSdkError):
    """``host()`` cannot bind the plugin: bad spec, unknown placement or grant."""

    code = "host_invalid"


class DesktopLifecycleAdapter:
    """The object a plugin's ``classFactory`` returns to QGIS."""

    def __init__(
        self,
        plugin_class: type,
        iface: object,
        *,
        context_factory: ContextFactory,
        instance_factory: PluginFactory | None = None,
    ) -> None:
        self._iface = iface
        self._context = context_factory(iface)
        self._runtime = PluginRuntime(
            plugin_class,
            self._context,
            instance_factory=instance_factory,
        )

    @property
    def iface(self) -> object:
        """Return the opaque host interface; never serialize or expose it."""
        return self._iface

    @property
    def context(self) -> PluginContext:
        """Return the context the runtime binds to the plugin."""
        return self._context

    @property
    def runtime(self) -> PluginRuntime:
        """Return the lifecycle owner for advanced adapters and tests."""
        return self._runtime

    def initGui(self) -> None:
        """Construct and bind the author plugin once; QGIS calls this."""
        self._runtime.start()

    def unload(self) -> None:
        """Dispose owned resources; repeated calls are safe."""
        self._runtime.unload()


def create_class_factory(
    plugin_class: type,
    *,
    context_factory: ContextFactory,
    instance_factory: PluginFactory | None = None,
) -> Callable[[object], DesktopLifecycleAdapter]:
    """Return a QGIS ``classFactory(iface)`` callable for one plugin class."""

    def class_factory(iface: object) -> DesktopLifecycleAdapter:
        return DesktopLifecycleAdapter(
            plugin_class,
            iface,
            context_factory=context_factory,
            instance_factory=instance_factory,
        )

    return class_factory


# -- host(): the generated classFactory ------------------------------------------


class MessageBarNotifications:
    """Informational messages on the QGIS message bar; dropped without ``iface``."""

    def __init__(self, iface: object | None, title: str) -> None:
        self._iface = iface
        self._title = title

    def info(self, message: str) -> None:
        if self._iface is None:
            return
        self._iface.messageBar().pushInfo(self._title, message)  # type: ignore[attr-defined]


def qgis_is_running() -> bool:
    """True inside a process that holds a ``QgsApplication``; never imports Qt otherwise."""
    try:
        core = importlib.import_module("qgis.core")
    except ImportError:
        return False
    return core.QgsApplication.instance() is not None


def default_context(
    iface: object | None, *, plugin_id: str, title: str
) -> PluginContext:
    """The capabilities the running host can offer, by host.

    Inside a ``QgsApplication`` every curated service is wired from PyQGIS and
    ``iface`` becomes ``ctx.desktop``; in a bare interpreter the context
    carries notifications and a scope, and ``require_<service>()`` refuses by
    name instead of failing obscurely.
    """
    scope = ResourceScope()
    notifications = MessageBarNotifications(iface, title)
    if qgis_is_running():
        from qgis_sdk.adapters.qgis import native_plugin_context

        return native_plugin_context(
            scope, settings_prefix=plugin_id, iface=iface, notifications=notifications
        )
    return PluginContext(notifications=notifications, scope=scope)


def resolve_plugin_spec(spec: str) -> type:
    """Import ``pkg.module:Class`` and return the class; typos fail by name.

    The module is imported through the builtin ``__import__`` rather than
    ``importlib``: QGIS tracks a plugin's modules by wrapping that builtin
    and drops exactly those on unload, so this is what keeps a reload from
    reusing a stale ``plugin`` module.
    """
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name.strip() or not attribute.strip():
        raise QgisSdkHostError(
            f"host() expects 'pkg.module:Class', got {spec!r} "
            "(for example field_tools.plugin:FieldTools)"
        )
    try:
        __import__(module_name)
    except ImportError as error:
        raise QgisSdkHostError(f"cannot import {module_name!r}: {error}") from error
    module = sys.modules[module_name]
    target: Any = module
    for part in attribute.split("."):
        target = getattr(target, part, None)
        if target is None:
            raise QgisSdkHostError(f"{module_name!r} has no attribute {attribute!r}")
    if not isinstance(target, type):
        raise QgisSdkHostError(f"{spec!r} is not a class")
    return target


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
        plugin_class: type,
        iface: object | None,
        *,
        context_factory: ContextFactory,
        title: str,
        view_id: str,
        placement: str | None,
        grants: tuple[str, ...],
        assets: Path,
        bindings: BindingsDescription | None = None,
        package_directory: Path | None = None,
    ) -> None:
        self._iface = iface
        self._title = title
        self._view_id = view_id
        self._placement = placement
        self._grants = grants
        self._assets = assets
        self._package_directory = package_directory or assets.parent
        self._action: Any | None = None
        self._view: Any | None = None
        self._bindings = (
            bindings if bindings is not None else describe_bindings(plugin_class)
        )
        self._surfaces: SurfaceHost | None = None
        self._desktop_bindings: DesktopBindings | None = None
        if qgis_is_running():
            from qgis_sdk.adapters.surfaces import DesktopBindings, SurfaceHost

            plugin_id = self._bindings.plugin_id
            self._surfaces = SurfaceHost(
                iface, plugin_id=plugin_id, title=title, bindings=self._bindings
            )
            self._desktop_bindings = DesktopBindings(
                iface,
                plugin_id=plugin_id,
                title=title,
                bindings=self._bindings,
                surfaces=self._surfaces,
                package_directory=self._package_directory,
            )
            context_factory = _with_ui(context_factory, self._surfaces)
        self._adapter = DesktopLifecycleAdapter(
            plugin_class, iface, context_factory=context_factory
        )

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
        self._adapter.unload()


def _with_ui(factory: ContextFactory, surfaces: SurfaceHost) -> ContextFactory:
    """Wrap ``factory`` so the context gains ``ui`` unless the author set one."""

    def with_ui(iface: object) -> PluginContext:
        context = factory(iface)
        if context.has("ui"):
            return context
        return context.with_services(ui=surfaces)

    return with_ui


def host(
    spec: str,
    *,
    placement: str | None = None,
    grants: Sequence[str] = (),
) -> Callable[[object | None], DesktopHost]:
    """Return the ``classFactory`` for the plugin class ``spec`` names.

    ``qgis-sdk build`` and ``qgis-sdk dev`` write the one line that calls
    this; an author never does. ``placement`` (``dock`` or ``dialog``) comes
    from ``[tool.qgis-sdk.web]`` and turns the page on; ``grants`` names the
    curated host operations the page may call - grants such as
    ``layers.read`` or single operation ids - none by default; the host
    keeps the operation ids they select. A class attribute
    ``context_factory`` on the plugin class replaces :func:`default_context`.
    """
    plugin_class = resolve_plugin_spec(spec)
    description = describe_plugin(plugin_class)
    bindings = describe_bindings(plugin_class)
    if placement is not None and placement not in PLACEMENTS:
        raise QgisSdkHostError(
            f"placement must be one of {', '.join(PLACEMENTS)}, got {placement!r}"
        )
    granted: tuple[str, ...] = ()
    if grants:
        from qgis_sdk.bridge.host import granted_operations

        try:
            granted = granted_operations(tuple(grants))
        except QgisSdkError as error:
            raise QgisSdkHostError(str(error)) from error
    if granted and placement is None:
        raise QgisSdkHostError("grants need a page; set placement as well")
    factory: ContextFactory | None = getattr(
        plugin_class, CONTEXT_FACTORY_ATTRIBUTE, None
    )
    if factory is None:
        factory = functools.partial(
            default_context, plugin_id=description.id, title=description.title
        )
    package_directory = _package_directory(plugin_class)
    assets = package_directory / ASSETS_DIRECTORY

    def classFactory(iface: object | None) -> DesktopHost:
        return DesktopHost(
            plugin_class,
            iface,
            context_factory=factory,
            title=description.title,
            view_id=f"{description.id}.main",
            placement=placement,
            grants=granted,
            assets=assets,
            bindings=bindings,
            package_directory=package_directory,
        )

    return classFactory


def _package_directory(plugin_class: type) -> Path:
    """The top-level package directory the class's module lives under.

    Read from the module's file, not the package's ``__file__``: under
    ``qgis-sdk dev`` the package's ``__init__`` is the generated host module
    in ``.qgis-sdk/dev/host`` while the sources - and ``web/`` - stay put.
    """
    module = importlib.import_module(plugin_class.__module__)
    file = getattr(module, "__file__", None)
    if file is None:
        raise QgisSdkHostError(f"{plugin_class.__module__} has no file to locate web/")
    depth = plugin_class.__module__.count(".")
    path = Path(file).resolve()
    return path.parents[max(depth - 1, 0)] if depth else path.parent
