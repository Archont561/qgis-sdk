"""The ``qgis-sdk`` commands, one private module each, registered on the shared app.

The modules are imported here in the order the commands appear in ``--help``;
importing one registers its command on :data:`app`.
"""

from __future__ import annotations

from qgis_sdk_tools._commands._app import app

# Importing a command module registers it; the order here is the order of
# ``--help`` and is kept as the single module had it .
# isort: off
from qgis_sdk_tools._commands import _new  # noqa: F401
from qgis_sdk_tools._commands import _bridge  # noqa: F401
from qgis_sdk_tools._commands import _processing  # noqa: F401
from qgis_sdk_tools._commands import _check  # noqa: F401
from qgis_sdk_tools._commands import _build  # noqa: F401
from qgis_sdk_tools._commands import _test  # noqa: F401
from qgis_sdk_tools._commands import _dev  # noqa: F401
from qgis_sdk_tools._commands import _targets  # noqa: F401
from qgis_sdk_tools._commands import _plugin  # noqa: F401
from qgis_sdk_tools._commands import _mcp  # noqa: F401

# isort: on
__all__ = ["app", "main"]


def main() -> None:
    """Run the command line; the wheel registers this as ``qgis-sdk``."""
    app()
