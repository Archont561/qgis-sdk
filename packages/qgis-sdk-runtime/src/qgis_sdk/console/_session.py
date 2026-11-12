"""The QGIS Python console as a client of the curated services (decision-48).

A developer looking at a running plugin has two things today: ``qgis.utils.iface``
- which the SDK keeps opaque everywhere (decision-9) - and a
``qgis.utils.plugins[name].runtime`` documented "for advanced adapters and
tests". Neither is an API. This module is the third: a session gets the *same*
``PluginContext`` a plugin gets (``layers``, ``project``, ``settings``,
``styles``, ``algorithms``, ``network``, ``notifications``, and ``desktop``
where the host has an ``iface``), and a plugin handle reaches that plugin's
actions and surfaces the way a page or a surface does - by id, validated, and
refused with the ids it would have needed.

Two routes, one object:

.. code-block:: python

    # in QGIS: Plugins > Python Console, for any plugin built with this SDK
    import qgis.utils
    session = qgis.utils.plugins["field_tools"].console()

    # anywhere the runtime is importable, against the whole Desktop
    from qgis_sdk.console import connect
    with connect() as session:
        session.ctx.layers.list_layers()
        session.plugin("field_tools").run("buffer", distance=25.0)

``iface`` stays behind ``ctx.desktop``: nothing here adds a wrapper that
re-exposes ``QgisInterface`` one method at a time, and nothing is imported into
the console namespace for you.

A handle does not need the plugin's own SDK copy to be the one running here. It
reads the object QGIS holds by attribute, so a plugin vendored with an older
runtime works while the attributes it has are the ones read, and refuses by
name for the rest (decision-39). No ``isinstance`` check crosses a vendored
copy, and a handle is not an authorization for one plugin to call another
(TASK-125).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, Self

from qgis_sdk.core import Host, PluginContext, PluginServices, ResourceScope
from qgis_sdk.environment import dev_request
from qgis_sdk.models import QgisSdkError

if TYPE_CHECKING:
    from qgis_sdk.console._handle import PluginHandle


def reload_phase1(qgis, self):
    if not (qgis.utils.loadPlugin(self._name) and qgis.utils.startPlugin(self._name)):
        raise QgisSdkConsoleError(
            f"{self._name} unloaded but QGIS could not load it again; see the "
            "QGIS message log, or restart `qgis-sdk dev`"
        )
    return f"{self._name} reloaded"


SURFACE_SUFFIXES: Final = ("_dialog", "_dock")


class QgisSdkConsoleError(QgisSdkError):
    """The console asked for a session, a plugin or a surface it cannot have."""

    code = "console_refused"


def connect(
    *,
    iface: object | None = None,
    settings_prefix: str = "console",
    notifications: Any = None,
) -> ConsoleSession:
    """Open a session over the running application's curated services.

    ``iface`` defaults to ``qgis.utils.iface``: on the Desktop ``ctx.desktop``
    then hands back the live interface object, and in a standalone
    ``QgsApplication`` - or a plain interpreter, where the session is still
    constructible - the same capability refuses by name while the services that
    need no interface keep working. The session owns the scope it builds, so
    closing it disposes what the session started and nothing a plugin owns.
    """
    scope = ResourceScope()
    return ConsoleSession(
        _context(
            scope,
            settings_prefix=settings_prefix,
            iface=iface if iface is not None else _desktop_iface(),
            notifications=notifications,
        ),
        owns_scope=True,
    )


def bind(adapter: object) -> ConsoleSession:
    """The session a plugin hands out for itself (``adapter.console()``).

    It borrows the plugin's context - the same service instances, so console and
    plugin read one project and one settings prefix - and owns no scope: the
    plugin's unload closes the session, and closing it here does not stop the
    plugin. This is what
    :meth:`~qgis_sdk.adapters.desktop.DesktopLifecycleAdapter.console` returns.
    """
    # Duck-typed on purpose: the plugin may have vendored another copy of this
    # package, so its ``PluginContext`` is a different class with the same shape.
    context = getattr(adapter, "context", None)
    if context is None or getattr(context, "scope", None) is None:
        raise QgisSdkConsoleError(
            f"{type(adapter).__name__} exposes no plugin context, so it cannot hand "
            "out a console session; a plugin loaded through `qgis-sdk dev` or the "
            "generated classFactory can"
        )
    description = getattr(getattr(adapter, "runtime", None), "description", None)
    return ConsoleSession(
        context, owns_scope=False, name=getattr(description, "id", None)
    )


def dev_session() -> bool:
    """Whether ``qgis-sdk dev`` started this process."""
    return dev_request() is not None


def _context(
    scope: ResourceScope,
    *,
    settings_prefix: str,
    iface: object | None,
    notifications: Any,
) -> PluginContext:
    """The context a console gets: every curated service, or the bare one."""
    from qgis_sdk.adapters.desktop import MessageBarNotifications, qgis_is_running

    if qgis_is_running():
        from qgis_sdk.adapters.qgis import NativeContextOptions, native_plugin_context

        return native_plugin_context(
            scope,
            NativeContextOptions(
                settings_prefix=settings_prefix,
                iface=iface,
                notifications=notifications,
            ),
        )
    return PluginContext(
        notifications
        if notifications is not None
        else MessageBarNotifications(None, settings_prefix),
        scope,
        PluginServices(host=Host.DESKTOP),
    )


def _desktop_iface() -> object | None:
    """``qgis.utils.iface`` while QGIS runs, else ``None``; imports no Qt."""
    try:
        import qgis.utils
    except ImportError:
        return None
    return getattr(qgis.utils, "iface", None)


def _loaded_plugins() -> Mapping[str, Any]:
    """``qgis.utils.plugins``, the mapping QGIS keeps loaded plugins in."""
    try:
        import qgis.utils
    except ImportError as error:
        raise QgisSdkConsoleError(
            "a plugin handle needs a running QGIS: start QGIS Desktop and use its "
            "Python console (or `qgis-sdk dev`), where qgis.utils.plugins exists"
        ) from error
    return getattr(qgis.utils, "plugins", {})


class ConsoleSession:
    """A console's view of the curated services, and of the plugins they serve.

    ``ctx`` is a full ``PluginContext``: reading a service this host cannot offer
    refuses by name, exactly as it does inside a plugin. A session from
    :func:`connect` owns the ``ResourceScope`` it built; a session a plugin
    handed out borrows that plugin's context and scope instead and never
    disposes what the plugin owns.
    """

    __slots__ = ("_closed", "_context", "_name", "_owns_scope")

    def __init__(
        self,
        context: PluginContext,
        *,
        owns_scope: bool,
        name: str | None = None,
    ) -> None:
        self._context = context
        self._owns_scope = owns_scope
        self._name = name
        self._closed = False

    @property
    def ctx(self) -> PluginContext:
        """The context the session's services live on."""
        self._ensure_open()
        return self._context

    @property
    def scope(self) -> ResourceScope:
        """The scope the session owns, or the plugin's scope it borrows."""
        return self._context.scope

    @property
    def plugin_name(self) -> str | None:
        """The plugin this session is bound to, ``None`` for a free session."""
        return self._name

    @property
    def owns_scope(self) -> bool:
        """Whether closing this session closes its scope (a free session does)."""
        return self._owns_scope

    @property
    def closed(self) -> bool:
        return self._closed

    def plugins(self) -> tuple[str, ...]:
        """The plugin names QGIS currently holds loaded, sorted."""
        self._ensure_open()
        return tuple(sorted(_loaded_plugins()))

    def plugin(self, name: str) -> PluginHandle:
        """The handle for the plugin QGIS loaded as ``name``."""
        from ._handle import PluginHandle

        self._ensure_open()
        loaded = _loaded_plugins()
        adapter = loaded.get(name)
        if adapter is None:
            known = ", ".join(sorted(loaded)) or "none"
            raise QgisSdkConsoleError(
                f"QGIS has no plugin named {name!r} loaded (loaded: {known})"
            )
        return PluginHandle(name, adapter, session=self)

    def close(self) -> None:
        """Dispose what the session started; a second close is a no-op.

        A session bound to a plugin owns nothing, so closing it only ends this
        view: the plugin keeps running on the same services.
        """
        if self._closed:
            return
        self._closed = True
        if self._owns_scope:
            self._context.scope.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __repr__(self) -> str:
        name = "free" if self._name is None else f"plugin={self._name!r}"
        return f"ConsoleSession({name}, {'closed' if self._closed else 'open'})"

    def _ensure_open(self) -> None:
        if self._closed:
            raise QgisSdkConsoleError(
                "this console session is closed; call connect() (or the plugin's "
                "console()) again"
            )
