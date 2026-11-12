"""``serverClassFactory``: the entry QGIS Server calls for Simple server.

QGIS Server does not load ``classFactory``. It imports this package and calls
``serverClassFactory(serverIface)``, which is what ``metadata.txt``'s
``server=True`` - written by `qgis-sdk build` from ``hosts = ["server"]`` -
tells it to do. The hooks themselves stay in ``plugin.py``; this file is the
only one that names the server adapter, and it imports it lazily so the package
still imports on a machine whose QGIS was built without QGIS Server
(``WITH_SERVER=OFF``), which is what lets ``qgis-sdk test`` prove the hooks
there.
"""

from __future__ import annotations

from qgis_sdk.server import ServerHooks as _ServerHooks

from .plugin import answer as _answer
from .plugin import default_version as _default_version
from .plugin import no_private_layers as _no_private_layers

HOOKS = _ServerHooks((_default_version, _answer, _no_private_layers))

__all__ = ["HOOKS", "serverClassFactory"]


def serverClassFactory(serverIface):
    """Register every hook with QGIS Server; it keeps what this returns."""
    from qgis_sdk.adapters.qgis.server import QgsServerHost

    return QgsServerHost(HOOKS, serverIface).register()
