"""The web page: a restricted Qt WebEngine view over this plugin's own bridge.

Qt and the SDK's native adapters are imported inside the functions, so
`qgis-sdk check` and the starter tests import this package without QGIS;
QGIS calls the functions with its ``iface``. The page may load files from
``web/`` only and reach no remote origin until you grant one in
``BrowserPolicy``.

Under `qgis-sdk dev` the Vite dev server serves the page instead, with hot
module replacement: the command puts its origin in ``QGIS_SDK_DEV_SERVER``
(``qgis_sdk.environment.DEV_SERVER_ENV``) for the QGIS process it starts, and
only there. A built plugin never sees the
variable and never reaches a dev server.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from qgis_sdk.bridge import Dispatcher
from qgis_sdk.environment import dev_server

ASSETS = Path(__file__).resolve().parent / "web"  # `bun run build` in web/ writes it
INDEX = ASSETS / "index.html"
VIEW_ID = "simple.main"
CHANNEL_OBJECT = "bridge"  # the name web/src/transport.ts looks up
TITLE = "Simple"


def add_toolbar_action(
    iface: Any, title: str, on_trigger: Callable[[], None]
) -> Any | None:
    """Put one button on the QGIS toolbar; a host without ``iface`` gets none."""
    if iface is None:
        return None
    from qgis.PyQt.QtWidgets import QAction

    action = QAction(title, iface.mainWindow())
    action.triggered.connect(lambda _checked=False: on_trigger())
    iface.addToolBarIcon(action)
    return action


def ask_for_directory(iface: Any, title: str) -> str:
    """Ask the user for a directory with the native dialog; empty when cancelled.

    This is where file authority comes from (decision-20): a picker the user
    answered on the host, never a path typed into the page.
    """
    from qgis.PyQt.QtWidgets import QFileDialog

    return QFileDialog.getExistingDirectory(iface.mainWindow(), title)


def remove_toolbar_action(iface: Any, action: Any | None) -> None:
    """Take the button down again on unload."""
    if iface is None or action is None:
        return
    iface.removeToolBarIcon(action)
    action.deleteLater()


def open_view(runtime: Any, iface: Any, *, placement: str) -> Any:
    """Build the page, its channel and the widget QGIS shows; return the widget.

    ``runtime`` is the SDK's ``PluginRuntime``: its description is the
    allowlist and its bound actions are the handlers, so the page can call
    exactly what ``plugin.py`` declares and nothing else.
    """
    from qgis.PyQt.QtCore import Qt, QUrl
    from qgis.PyQt.QtWebChannel import QWebChannel
    from qgis.PyQt.QtWidgets import QDialog, QDockWidget, QVBoxLayout
    from qgis_sdk.adapters.webchannel import create_channel_object
    from qgis_sdk.adapters.webengine import (
        BrowserPolicy,
        create_restricted_page,
        create_webengine_view,
    )

    served_from = dev_server()
    dispatcher = Dispatcher.from_runtime(
        runtime, authorize=lambda binding, operation: binding.view_id == VIEW_ID
    )
    binding = dispatcher.bind(view_id=VIEW_ID, origin=served_from or ASSETS.as_uri())
    policy = BrowserPolicy(
        origins=() if served_from is None else (served_from,),
        asset_roots=(ASSETS,) if ASSETS.is_dir() else (),
    )
    view = create_webengine_view()
    page = create_restricted_page(policy, parent=view)
    channel = QWebChannel(page)
    channel.registerObject(
        CHANNEL_OBJECT, create_channel_object(dispatcher, binding, parent=page)
    )
    page.setWebChannel(channel)
    view.setPage(page)
    if served_from is not None:
        page.load(QUrl(served_from + "/"))
    elif INDEX.is_file():
        page.load(QUrl.fromLocalFile(str(INDEX)))
    else:
        page.setHtml(
            f"<p>No built page at <code>{INDEX}</code>. "
            "Run <code>bun run build</code> in <code>web/</code> first.</p>"
        )

    parent = None if iface is None else iface.mainWindow()
    if placement == "dock":
        dock = QDockWidget(TITLE, parent)
        dock.setObjectName(VIEW_ID)
        dock.setWidget(view)
        if iface is not None:
            iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        return dock
    dialog = QDialog(parent)
    dialog.setWindowTitle(TITLE)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view)
    dialog.resize(720, 540)
    return dialog


def close_view(widget: Any, iface: Any) -> None:
    """Close the page and release the widget, dock or dialog alike."""
    from qgis.PyQt.QtWidgets import QDockWidget

    if iface is not None and isinstance(widget, QDockWidget):
        iface.removeDockWidget(widget)
    widget.close()
    widget.deleteLater()
