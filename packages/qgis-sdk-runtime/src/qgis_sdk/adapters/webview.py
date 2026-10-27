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
from pathlib import Path
from typing import Any, Final

from qgis_sdk.adapters.palette import palette_theme
from qgis_sdk.bridge import Dispatcher
from qgis_sdk.core import PluginContext
from qgis_sdk.environment import dev_server

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
    from qgis.PyQt.QtWidgets import QAction

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
    runtime: Any,
    context: PluginContext,
    iface: Any,
    *,
    title: str,
    view_id: str,
    placement: str,
    assets: Path,
    grants: Sequence[str] = (),
) -> Any:
    """Build the page, its channel and the widget QGIS shows; return the widget.

    ``runtime`` is the started ``PluginRuntime``: its description is the
    allowlist and its bound handlers answer, so the page calls exactly what
    the plugin declares. ``grants`` adds the curated host operations the
    project named (``register_host_operations(only=grants)``), served from
    the very services ``context`` carries; no grants, no host operation.
    ``assets`` is the directory the built page lives in (``<package>/web``).
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

    if placement not in PLACEMENTS:
        raise ValueError(f"placement must be one of {PLACEMENTS}, got {placement!r}")
    served_from = dev_server()
    index = assets / "index.html"
    dispatcher = Dispatcher.from_runtime(
        runtime,
        authorize=lambda binding, operation: binding.view_id == view_id,
        theme=palette_theme,
    )
    if grants:
        from qgis_sdk.bridge.host import (
            HostServices,
            granted_operations,
            register_host_operations,
        )

        register_host_operations(
            dispatcher,
            HostServices.from_context(context),
            only=granted_operations(tuple(grants)),
        )
    binding = dispatcher.bind(view_id=view_id, origin=served_from or assets.as_uri())
    policy = BrowserPolicy(
        origins=() if served_from is None else (served_from,),
        asset_roots=(assets,) if assets.is_dir() else (),
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
    elif index.is_file():
        page.load(QUrl.fromLocalFile(str(index)))
    else:
        page.setHtml(
            f"<p>No built page at <code>{index}</code>. "
            "Run the web build in <code>web/</code> first.</p>"
        )

    parent = None if iface is None else iface.mainWindow()
    if placement == "dock":
        dock = QDockWidget(title, parent)
        dock.setObjectName(view_id)
        dock.setWidget(view)
        if iface is not None:
            iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        return dock
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view)
    dialog.resize(*DIALOG_SIZE)
    return dialog


def close_view(widget: Any, iface: Any) -> None:
    """Close the page and release the widget, dock or dialog alike."""
    from qgis.PyQt.QtWidgets import QDockWidget

    if iface is not None and isinstance(widget, QDockWidget):
        iface.removeDockWidget(widget)
    widget.close()
    widget.deleteLater()
