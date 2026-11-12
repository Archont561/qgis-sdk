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

import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from qgis_sdk.bindings import BindingsDescription
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
ContextFactory = Callable[[object | None], PluginContext]
"""Build the plugin context from the host's opaque Desktop ``iface``."""
CONTEXT_FACTORY_ATTRIBUTE: Final = "context_factory"
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
        from qgis.PyQt.QtCore import QTimer  # noqa: F401 - the import is the probe
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


def desktop_surfaces(
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
