"""The page view a hosted plugin shows: a restricted Qt WebEngine view over its bridge.

decision-43 makes this the first host-owned surface: a project declares
``[tool.qgis-sdk.web]`` and :func:`qgis_sdk.adapters.desktop.host` opens the
built page here, in a dock or a dialog, with the plugin's own declared
operations and the curated host operations the project granted. Nothing in
an author's package touches Qt for it.

Qt is imported inside the functions, so the module loads without QGIS and
the pure tests import it freely. The page may load files from the package's
``web/`` directory only and reaches no remote origin; under ``qgis-sdk dev``
the Vite dev server named by ``QGIS_SDK_DEV_SERVER`` serves it instead, with
hot module replacement, and is the one origin granted then.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypedDict, Unpack

from qgis_sdk.adapters.palette import palette_theme
from qgis_sdk.bridge import Dispatcher
from qgis_sdk.core import PluginContext
from qgis_sdk.environment import dev_server


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_open_view_p1(_s):
    _s.values = _OpenValues1(**_s.options)
    from qgis.PyQt.QtCore import Qt, QUrl

    _s.Qt = Qt
    _s.QUrl = QUrl
    from qgis.PyQt.QtWebChannel import QWebChannel

    _s.QWebChannel = QWebChannel
    from qgis.PyQt.QtWidgets import QDialog, QDockWidget, QVBoxLayout

    _s.QDialog = QDialog
    _s.QDockWidget = QDockWidget
    _s.QVBoxLayout = QVBoxLayout

    from qgis_sdk.adapters.webchannel import create_channel_object

    _s.create_channel_object = create_channel_object
    from qgis_sdk.adapters.webengine import (
        BrowserPolicy,
        create_restricted_page,
        create_webengine_view,
    )

    _s.BrowserPolicy = BrowserPolicy
    _s.create_restricted_page = create_restricted_page
    _s.create_webengine_view = create_webengine_view


def _cc_open_view_p2(_s):

    if _s.values.placement not in PLACEMENTS:
        raise ValueError(
            f"placement must be one of {PLACEMENTS}, got {_s.values.placement!r}"
        )
    _s.served_from = dev_server()
    _s.index = _s.values.assets / "index.html"
    _s.dispatcher = Dispatcher.from_runtime(
        _s.runtime,
        authorize=lambda binding, operation: binding.view_id == _s.values.view_id,
        theme=palette_theme,
    )


def _cc_open_view_p3(_s):
    if _s.values.grants:
        from qgis_sdk.bridge.host import (
            HostServices,
            granted_operations,
            register_host_operations,
        )

        _s.HostServices = HostServices
        _s.granted_operations = granted_operations
        _s.register_host_operations = register_host_operations

        _s.register_host_operations(
            _s.dispatcher,
            _s.HostServices.from_context(_s.context),
            only=_s.granted_operations(tuple(_s.values.grants)),
        )


def _cc_open_view_p4(_s):
    _s.binding = _s.dispatcher.bind(
        view_id=_s.values.view_id, origin=_s.served_from or _s.values.assets.as_uri()
    )
    _s.policy = _s.BrowserPolicy(
        origins=() if _s.served_from is None else (_s.served_from,),
        asset_roots=(_s.values.assets,) if _s.values.assets.is_dir() else (),
    )
    _s.view = _s.create_webengine_view()
    _s.page = _s.create_restricted_page(_s.policy, parent=_s.view)
    _s.channel = _s.QWebChannel(_s.page)


def _cc_open_view_p5(_s):
    _s.channel.registerObject(
        CHANNEL_OBJECT,
        _s.create_channel_object(_s.dispatcher, _s.binding, parent=_s.page),
    )
    _s.page.setWebChannel(_s.channel)
    _s.view.setPage(_s.page)


def _cc_open_view_p6(_s):
    if _s.served_from is not None:
        _s.page.load(_s.QUrl(_s.served_from + "/"))
    elif _s.index.is_file():
        _s.page.load(_s.QUrl.fromLocalFile(str(_s.index)))
    else:
        _s.page.setHtml(
            f"<p>No built page at <code>{_s.index}</code>. "
            "Run the web build in <code>web/</code> first.</p>"
        )

    _s.parent = None if _s.iface is None else _s.iface.mainWindow()


def _cc_open_view_p7(_s):
    if _s.values.placement == "dock":
        _s.dock = _s.QDockWidget(_s.values.title, _s.parent)
        _s.dock.setObjectName(_s.values.view_id)
        _s.dock.setWidget(_s.view)
        if _s.iface is not None:
            _s.iface.addDockWidget(_s.Qt.DockWidgetArea.RightDockWidgetArea, _s.dock)
        return _CcReturn(_s.dock)
    _s.dialog = _s.QDialog(_s.parent)
    return _CcReturn(
        _open_view_phase1(_s.QVBoxLayout, _s.dialog, _s.values.title, _s.view)
    )


def _open_view_phase1(QVBoxLayout, dialog, title, view):
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view)
    dialog.resize(*DIALOG_SIZE)
    return dialog


__all__ = [
    "CHANNEL_OBJECT",
    "PLACEMENTS",
    "add_toolbar_action",
    "close_view",
    "open_view",
    "remove_toolbar_action",
]

#: The channel object name ``QgisSdk.fromBridgeSchema`` connects to by default.
CHANNEL_OBJECT: Final = "bridge"
#: Where QGIS shows the page.
PLACEMENTS: Final = ("dock", "dialog")
DIALOG_SIZE: Final = (720, 540)


def add_toolbar_action(
    iface: Any, title: str, on_trigger: Callable[[], None]
) -> Any | None:
    """Put one button on the QGIS toolbar; a host without ``iface`` gets none."""
    if iface is None:
        return None
    from qgis_sdk.adapters._qt import action_class

    QAction = action_class()

    action = QAction(title, iface.mainWindow())
    action.triggered.connect(lambda _checked=False: on_trigger())
    iface.addToolBarIcon(action)
    return action


def remove_toolbar_action(iface: Any, action: Any | None) -> None:
    """Take the button down again on unload."""
    if iface is None or action is None:
        return
    iface.removeToolBarIcon(action)
    action.deleteLater()


def open_view(
    runtime: Any, context: PluginContext, iface: Any, **options: Unpack[_OpenOptions1]
) -> Any:
    """Build the page, its channel and the widget QGIS shows; return the widget.

    ``runtime`` is the started ``PluginRuntime``: its description is the
    allowlist and its bound handlers answer, so the page calls exactly what
    the plugin declares. ``grants`` adds the curated host operations the
    project named (``register_host_operations(only=grants)``), served from
    the very services ``context`` carries; no grants, no host operation.
    ``assets`` is the directory the built page lives in (``<package>/web``).
    """
    _s = _CcState(runtime=runtime, context=context, iface=iface, options=options)
    for _p in (
        _cc_open_view_p1,
        _cc_open_view_p2,
        _cc_open_view_p3,
        _cc_open_view_p4,
        _cc_open_view_p5,
        _cc_open_view_p6,
        _cc_open_view_p7,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def close_view(widget: Any, iface: Any) -> None:
    """Close the page and release the widget, dock or dialog alike."""
    from qgis.PyQt.QtWidgets import QDockWidget

    if iface is not None and isinstance(widget, QDockWidget):
        iface.removeDockWidget(widget)
    widget.close()
    widget.deleteLater()


class _OpenOptions1(TypedDict, total=False):
    title: str
    view_id: str
    placement: str
    assets: Path
    grants: Sequence[str]


@dataclass(frozen=True, slots=True)
class _OpenValues1:
    title: str
    view_id: str
    placement: str
    assets: Path
    grants: Sequence[str] = ()
