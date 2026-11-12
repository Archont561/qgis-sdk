from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qgis_sdk.core import PluginContext
from qgis_sdk.models import QgisSdkError

from ._session import (
    SURFACE_SUFFIXES,
    ConsoleSession,
    QgisSdkConsoleError,
    dev_session,
    reload_phase1,
)


class _PluginHandleMixin1:
    @property
    def name(self) -> str:
        """The name QGIS loaded the plugin under."""
        return self._name

    @property
    def runtime(self) -> Any:
        """The plugin's runtime object, opaque outside this module."""
        return self._adapter_runtime()

    @property
    def ctx(self) -> PluginContext:
        """The context the plugin runs on: the same service instances as its own."""
        context = getattr(self._adapter, "context", None)
        if context is not None and getattr(context, "scope", None) is not None:
            return context
        return self._read("context")

    @property
    def description(self) -> Any:
        """The validated declaration: id, title, version, actions and streams."""
        return self._read("description")

    @property
    def actions(self) -> tuple[str, ...]:
        """The action ids the plugin declares, sorted."""
        return tuple(sorted(self._ids("actions")))

    @property
    def streams(self) -> tuple[str, ...]:
        """The stream ids the plugin declares, sorted."""
        return tuple(sorted(self._ids("streams")))

    @property
    def algorithms(self) -> tuple[str, ...]:
        """The Processing ids it registered, ``provider:algorithm``, sorted."""
        return tuple(sorted(self._read("algorithms")))

    @property
    def state(self) -> Any:
        """The lifecycle state (``running``, ``stopped`` ...) as the runtime gives it."""
        return self._read("state")

    def surfaces(self) -> tuple[str, ...]:
        """The surface ids the plugin declares, in declaration order."""
        return tuple(entry.id for entry in self._surface_entries())

    def run(self, action_id: str, /, **inputs: object) -> object:
        """Call ``action_id`` with validated ``inputs``; return the handler's result.

        The inputs take the bridge dispatcher's path (decision-27): the value
        becomes wire data (a Qt object or a live layer is refused there, not
        half-validated), is checked against the request schema the declaration
        already published, and only then is spread as keyword arguments - so an
        unknown field, a missing one or a value of the wrong type is refused
        with the ``QgisSdkBridgeError`` a page would see, naming the field.

        A handler that raises is *not* wrapped: in a console the traceback of
        the plugin's own exception is what a developer needs, and it points at
        the plugin's line rather than at this module. Nothing is threaded: the
        handler runs here, so a call blocks the GUI exactly as pressing the
        plugin's button would.
        """
        action = self._action(action_id)
        payload = _validated_payload(action, inputs)
        handler = self._read("actions").get(action.id)
        if handler is None:
            raise QgisSdkConsoleError(
                f"{self._name}: action {action.id!r} is declared but has no handler "
                f"bound; the plugin is {self._state_text()}"
            )
        return handler(**payload)

    def open(self, target: str) -> Any:
        """Open one of the plugin's surfaces and return the surface instance.

        ``target`` is a surface id (``buffer_dialog``), a surface class name
        (``BufferDialog``), or an action id whose surface follows the scaffold's
        naming - ``buffer`` for ``BufferDialog`` or ``buffer_dialog``. The
        surface is opened by the plugin's own host, so it gets the plugin's
        context, scope and lifetime (decision-55's trigger rule); an unknown
        name refuses listing the ids the plugin declares. Like every window in
        QGIS this belongs on the GUI thread, which is the console's thread.
        """
        entry = self._resolve_surface(target)
        host = getattr(self._adapter, "surfaces", None)
        if host is None:
            raise QgisSdkConsoleError(
                f"{self._name}: this host opened no surfaces; run the plugin inside "
                "QGIS (`qgis-sdk dev`, or the generated classFactory)"
            )
        self._ensure_gui_thread()
        return host.open(entry.cls)

    def reload(self) -> str:
        """Unload and load this plugin again; only inside ``qgis-sdk dev``.

        The policy is decision-15's: the running revision is asked to quiesce
        first, and a plugin with work in flight is left as it is rather than cut
        off mid-run. An installed plugin refuses by name, because there is no
        source tree for a reload to pick up.
        """
        if not dev_session():
            raise QgisSdkConsoleError(
                "reload() is a development operation: it needs a QGIS started by "
                "`qgis-sdk dev` (QGIS_SDK_DEV_REQUEST is not set in this process)"
            )
        state = self._state_text()
        quiesce = getattr(self.runtime, "quiesce", None)
        if callable(quiesce):
            outcome = quiesce()
            if getattr(outcome, "refused", False):
                blockers = "; ".join(getattr(outcome, "blockers", ()) or ())
                raise QgisSdkConsoleError(
                    f"{self._name} cannot be reloaded while it is working: "
                    f"{blockers or 'unknown work'}; finish or cancel it and try again"
                )
        import qgis.utils

        if not qgis.utils.unloadPlugin(self._name):
            raise QgisSdkConsoleError(f"{self._name} ({state}) refused to unload")
        return reload_phase1(qgis, self)

    # -- what the plugin exposes -----------------------------------------------------

    def _adapter_runtime(self) -> Any:
        """The runtime the adapter holds, refusing an adapter that holds none."""
        runtime = getattr(self._adapter, "runtime", None)
        if runtime is None:
            raise QgisSdkConsoleError(
                f"{self._name}: what QGIS holds for this plugin is "
                f"{type(self._adapter).__name__}, which exposes no 'runtime'; a "
                "handle needs a plugin built by this SDK or a compatible one"
            )
        return runtime


class _PluginHandleMixin2:
    def _read(self, attribute: str) -> Any:
        """Read ``attribute`` from the plugin's runtime, refusing by name."""
        value = getattr(self._adapter_runtime(), attribute, None)
        if value is None:
            raise QgisSdkConsoleError(
                f"{self._name}: its runtime has no {attribute!r} (built by an older "
                "qgis-sdk); raise the plugin's runtime requirement"
            )
        return value

    def _ids(self, attribute: str) -> tuple[str, ...]:
        declared = getattr(self.description, attribute, None) or ()
        return tuple(str(getattr(entry, "id", entry)) for entry in declared)

    def _action(self, action_id: str) -> Any:
        for action in getattr(self.description, "actions", None) or ():
            if getattr(action, "id", None) == action_id:
                return action
        known = ", ".join(self._ids("actions")) or "none"
        raise QgisSdkConsoleError(
            f"{self._name} declares no action named {action_id!r} (declared: {known})"
        )

    def _surface_entries(self) -> tuple[Any, ...]:
        bindings = getattr(self._adapter, "bindings", None)
        if bindings is None:
            raise QgisSdkConsoleError(
                f"{self._name}: {type(self._adapter).__name__} places no surfaces; a "
                "plugin loaded through `qgis-sdk dev` or the generated "
                "classFactory does"
            )
        declared = getattr(bindings, "surfaces", None)
        if declared is None:
            raise QgisSdkConsoleError(
                f"{self._name}: its bindings have no 'surfaces' (built by an older "
                "qgis-sdk); raise the plugin's runtime requirement"
            )
        return tuple(declared)

    def _resolve_surface(self, target: str) -> Any:
        """The registered surface ``target`` names, or a refusal listing them."""
        entries = self._surface_entries()
        for entry in entries:
            if entry.id == target or getattr(entry.cls, "__name__", None) == target:
                return entry
        for suffix in SURFACE_SUFFIXES:
            for entry in entries:
                if entry.id == f"{target}{suffix}":
                    return entry
        known = ", ".join(entry.id for entry in entries) or "none"
        actions = ", ".join(self._ids("actions")) or "none"
        raise QgisSdkConsoleError(
            f"{self._name} opens no surface named {target!r} (surfaces: {known}); "
            f"its actions are {actions}"
        )

    def _state_text(self) -> str:
        state = getattr(self.runtime, "state", None)
        return str(getattr(state, "value", state))

    def _ensure_gui_thread(self) -> None:
        """Refuse a window built off the GUI thread, where Qt would crash."""
        from qgis_sdk.adapters.desktop import qgis_is_running

        if not qgis_is_running():
            return
        from qgis.core import QgsApplication
        from qgis.PyQt.QtCore import QThread

        application = QgsApplication.instance()
        if application is None or QThread.currentThread() is application.thread():
            return
        raise QgisSdkConsoleError(
            "a plugin surface opens on the GUI thread; run this from the QGIS Python "
            "console rather than a worker thread"
        )


class PluginHandle(_PluginHandleMixin1, _PluginHandleMixin2):
    """One running plugin, reached the way a page and a surface reach it.

    Everything is read from the object QGIS holds for the plugin - what
    ``classFactory`` returned - so a plugin built by another SDK version is
    usable while it offers the attributes read here, and refuses by name for
    the rest. Nothing is imported from the plugin's own vendored copy.
    """

    __slots__ = ("_adapter", "_name", "_session")

    def __init__(self, name: str, adapter: Any, *, session: ConsoleSession) -> None:
        self._name = name
        self._adapter = adapter
        self._session = session

    def __repr__(self) -> str:
        try:
            state = self._state_text()
        except QgisSdkError:  # pragma: no cover - an adapter without a runtime
            state = "unknown"
        return f"PluginHandle({self._name!r}, state={state!r})"


def _validated_payload(action: Any, inputs: Mapping[str, object]) -> dict[str, Any]:
    """``inputs`` as the bridge dispatcher would hand them to a handler.

    A console call is a bridge call without the transport, so it takes the same
    steps in the same order: the value becomes wire data, then it is checked
    against the request schema the declaration published, then a file ref the
    schema allows is rebuilt as the ``FileRef`` a handler declared.
    """
    from qgis_sdk.bridge.protocol import to_wire
    from qgis_sdk.bridge.schema import validate
    from qgis_sdk.models.files import FILE_REF_KINDS, FileRef

    payload = to_wire(dict(inputs))
    schema = getattr(action, "request", None)
    if schema:
        validate(payload, schema, path="payload")
    return {
        name: (
            FileRef.from_wire(value)
            if isinstance(value, Mapping) and value.get("kind") in FILE_REF_KINDS
            else value
        )
        for name, value in payload.items()
    }
