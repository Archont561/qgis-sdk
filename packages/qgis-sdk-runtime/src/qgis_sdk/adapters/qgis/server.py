"""Where a plugin author finds the QGIS Server host: ``qgis_sdk.adapters.qgis``.

The class itself lives in :mod:`qgis_sdk.adapters._server`, beside the mapping it
uses, because nothing in it imports Qt at module import: it takes a
``QgsServerInterface`` and asks for ``qgis.server`` only when a host is actually
built. That is what lets the wiring be tested on a machine with no QGIS, and it
is why this module is a re-export rather than a second copy.

    from qgis_sdk.adapters.qgis.server import QgsServerHost

    def serverClassFactory(serverIface):
        return QgsServerHost(ServerHooks(my_plugin.server_hooks()), serverIface).register()
"""

from qgis_sdk.adapters._server import QgsServerHost, qgis_server

__all__ = ["QgsServerHost", "qgis_server"]
