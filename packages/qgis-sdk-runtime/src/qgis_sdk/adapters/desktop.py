"""Desktop lifecycle glue for QGIS ``classFactory``/``initGui``/``unload``.

Two layers. :class:`DesktopLifecycleAdapter` and :func:`create_class_factory`
delegate construction and disposal to :class:`PluginRuntime` and know nothing
about QGIS: the host passes ``iface`` and a ``context_factory`` supplies the
typed capabilities. :func:`host` is what a generated plugin binds
(decision-43): ``classFactory = host("pkg.plugin:app")`` resolves the
author's application, builds the context the running host can offer - every
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
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from qgis_sdk.bindings import BindingsDescription, describe_bindings
from qgis_sdk.core import (
    Host,
    PluginContext,
    PluginRuntime,
    PluginServices,
    ResourceScope,
)
from qgis_sdk.core._application import QgisSdkPlugin
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.models import QgisSdkError
from qgis_sdk.services import Notification, NotificationsBase

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

ContextFactory = Callable[[object | None], PluginContext]
"""Build the plugin context from the host's opaque Desktop ``iface``."""

#: An application may bind this to a callable ``(iface) -> PluginContext`` to
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
        app: QgisSdkPlugin,
        iface: object | None,
        *,
        context_factory: ContextFactory,
    ) -> None:
        if not isinstance(app, QgisSdkPlugin):
            raise QgisSdkDeclarationError(
                "DesktopLifecycleAdapter requires a QgisSdkPlugin"
            )
        self._iface = iface
        self._context = context_factory(iface)
        self._runtime = PluginRuntime(app, self._context)
        self._sessions: list[Any] = []
        self._job_pump: Any = None
        self._layout_pump: Any = None
        self._algorithms_pump: Any = None

    @property
    def iface(self) -> object | None:
        """Return the opaque host interface; never serialize or expose it."""
        return self._iface

    @property
    def context(self) -> PluginContext:
        """Return the context the runtime binds to the plugin.

        Read back from the runtime rather than kept here: the runtime adds
        ``jobs`` to the context it was given when the plugin declares any
        (TASK-116), and every surface must be built from the context the
        plugin itself reads.
        """
        return self._runtime.context

    @property
    def runtime(self) -> PluginRuntime:
        """Return the lifecycle owner for advanced adapters and tests."""
        return self._runtime

    @property
    def job_pump(self) -> Any | None:
        """The timer that delivers this plugin's job callbacks, once it runs."""
        return self._job_pump

    def console(self) -> Any:
        """Return a console session bound to this plugin's own context.

        The session shares the plugin's service instances - one project, one
        settings prefix, one ``ctx.desktop`` - so what a developer types in the
        QGIS Python console reads and changes exactly what the plugin does
        (decision-48). Closing it does not stop the plugin, and the plugin's
        unload closes it.
        """
        from qgis_sdk import console

        session = console.bind(self)
        self._sessions.append(session)
        return session

    def initGui(self) -> None:
        """Construct and bind the author plugin once; QGIS calls this."""
        self._runtime.start()
        self._start_job_pump()

    def _pump_services(self) -> list[tuple[str, object, str | None]]:
        """The three services a pump may tick, with their pump attribute and name."""
        context = self._context
        jobs = self._runtime.jobs
        layouts = context.layouts if context.has("layouts") else None
        algorithms = context.algorithms if context.has("algorithms") else None
        specs: list[tuple[str, object, str | None]] = []
        if jobs is not None:
            specs.append(("_job_pump", jobs, None))
        if layouts is not None:
            specs.append(("_layout_pump", layouts.jobs, "layouts-job-pump"))
        if algorithms is not None:
            # A batch submits to the algorithms service's own job service,
            # which needs its own tick whether or not the plugin declares jobs
            # of its own (TASK-94).
            specs.append(("_algorithms_pump", algorithms.jobs, "algorithms-job-pump"))
        return specs

    def _start_job_pump(self) -> None:
        """Tick the plugin's jobs on the GUI thread while it runs (TASK-116).

        Two services can need a tick: the plugin's own ``ctx.jobs``, when it
        declares one, and the layouts service's, which submits an export as a
        task in the task bar whether or not the plugin declares jobs of its
        own (TASK-89). One pump each, both stopped on unload.
        """
        specs = self._pump_services()
        if not specs or not _qt_running():
            # A host without the Qt bindings - the reference workflow's own pure
            # tests, a fake-backed runtime - has no event loop to tick on: the
            # test drives its jobs by hand, so there is nothing to pump.
            return
        from qgis_sdk.adapters.qgis.jobs import QgsJobPump

        for attribute, service, name in specs:
            pump = (
                QgsJobPump(service) if name is None else QgsJobPump(service, name=name)
            )
            pump.start()
            setattr(self, attribute, pump)

    def unload(self) -> None:
        """Dispose owned resources; repeated calls are safe."""
        if self._job_pump is not None:
            # Stop delivery before anything the callbacks read is disposed.
            self._job_pump.stop()
            self._job_pump = None
        if self._layout_pump is not None:
            self._layout_pump.stop()
            self._layout_pump = None
        if self._algorithms_pump is not None:
            self._algorithms_pump.stop()
            self._algorithms_pump = None
        sessions, self._sessions = self._sessions, []
        for session in sessions:
            session.close()
        self._runtime.unload()


def _qt_running() -> bool:
    """Whether this process has the Qt bindings a job pump is built on."""
    try:
        from qgis.PyQt.QtCore import QTimer  # noqa: F401
    except ImportError:
        return False
    return True


def create_class_factory(
    app: QgisSdkPlugin,
    *,
    context_factory: ContextFactory,
) -> Callable[[object | None], DesktopLifecycleAdapter]:
    """Return a QGIS ``classFactory(iface)`` callable for one application."""
    if not isinstance(app, QgisSdkPlugin):
        raise QgisSdkDeclarationError("create_class_factory requires a QgisSdkPlugin")

    def class_factory(iface: object | None) -> DesktopLifecycleAdapter:
        return DesktopLifecycleAdapter(app, iface, context_factory=context_factory)

    return class_factory


# -- host(): the generated classFactory ------------------------------------------


class MessageBarNotifications(NotificationsBase):
    """Messages on the QGIS message bar at their level; dropped without ``iface``.

    A ``with_action`` button is a ``QPushButton`` on the bar item that runs
    the plugin's action through what :meth:`bind_actions` was given - the
    host binds ``runtime.actions`` once the plugin has started.
    """

    def __init__(self, iface: object | None, title: str) -> None:
        self._iface = iface
        self._title = title
        self._dispatch: list[Callable[..., object] | None] = [None]

    def bind_actions(self, dispatch: Callable[..., object] | None) -> None:
        """Route button presses to ``dispatch(action_id, **arguments)``."""
        self._dispatch[0] = dispatch

    def _deliver(self, notification: Notification) -> None:
        if self._iface is None:
            return
        from qgis.PyQt.QtWidgets import QPushButton

        from qgis_sdk.adapters.qgis.notifications import LEVEL_MAP

        bar = self._iface.messageBar()  # type: ignore[attr-defined]
        item = bar.createMessage(self._title, notification.message)
        action = notification.action
        if action is not None:
            button = QPushButton(action.label, item)
            button.setObjectName(f"notifications/{action.action_id}")
            dispatch = self._dispatch

            def press(_checked: bool = False) -> None:
                if dispatch[0] is None:
                    return
                dispatch[0](action.action_id, **action.arguments)

            button.clicked.connect(press)
            item.layout().addWidget(button)
        bar.pushWidget(item, LEVEL_MAP[notification.level])


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
        from qgis_sdk.adapters.qgis import NativeContextOptions, native_plugin_context

        return native_plugin_context(
            scope,
            NativeContextOptions(
                settings_prefix=plugin_id, iface=iface, notifications=notifications
            ),
        )
    return PluginContext(notifications, scope, PluginServices(host=Host.DESKTOP))


def resolve_plugin_spec(spec: str) -> QgisSdkPlugin:
    """Import ``pkg.module:app`` and return the application; typos fail by name.

    The module is imported through the builtin ``__import__`` rather than
    ``importlib``: QGIS tracks a plugin's modules by wrapping that builtin
    and drops exactly those on unload, so this is what keeps a reload from
    reusing a stale ``plugin`` module.
    """
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name.strip() or not attribute.strip():
        raise QgisSdkHostError(
            f"host() expects 'pkg.module:app', got {spec!r} "
            "(for example field_tools.plugin:app)"
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
    if not isinstance(target, QgisSdkPlugin):
        raise QgisSdkHostError(f"{spec!r} is not a QgisSdkPlugin")
    return target


@dataclass(frozen=True, slots=True)
class DesktopHostOptions:
    """The keyword half of a :class:`DesktopHost` construction.

    The generated ``classFactory`` passes one record rather than positional
    field after field, so the page, placement and grant declarations stay
    together (decision-81).
    """

    context_factory: ContextFactory
    title: str
    view_id: str
    placement: str | None
    grants: tuple[str, ...]
    assets: Path
    bindings: BindingsDescription | None = None
    package_directory: Path | None = None


def _desktop_surfaces(
    iface: object | None,
    bindings: BindingsDescription,
    title: str,
    package_directory: Path,
) -> tuple[SurfaceHost | None, DesktopBindings | None]:
    """Build the Desktop bindings only inside a running QGIS."""
    if not qgis_is_running():
        return None, None
    from qgis_sdk.adapters.surfaces import DesktopBindings, SurfaceHost

    plugin_id = bindings.plugin_id
    surfaces = SurfaceHost(iface, plugin_id=plugin_id, title=title, bindings=bindings)
    desktop = DesktopBindings(
        iface,
        plugin_id=plugin_id,
        title=title,
        bindings=bindings,
        surfaces=surfaces,
        package_directory=package_directory,
    )
    return surfaces, desktop


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
        self._surfaces, self._desktop_bindings = _desktop_surfaces(
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
