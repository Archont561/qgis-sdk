"""Environment variable names shared between the developer tools and a plugin.

``qgis-sdk dev`` and ``qgis-sdk test`` (``qgis_sdk_tools``) set these in the
QGIS process they start; code generated into a plugin reads them. They are
defined once, here, in the runtime, so the two sides can never disagree about
a name (decision-35). Nothing in the runtime *acts* on them: a built plugin
that never sees the variables behaves exactly as one that does not know them.
"""

from __future__ import annotations

import os
from typing import Final

__all__ = [
    "DEV_REQUEST_ENV",
    "DEV_SERVER_ENV",
    "TEST_TARGET_ENV",
    "dev_request",
    "dev_server",
]

#: The origin of the Vite dev server ``qgis-sdk dev`` started for a web UI,
#: for example ``http://127.0.0.1:5173``; only ever set by the command, so a
#: production build never reaches a dev server.
DEV_SERVER_ENV: Final = "QGIS_SDK_DEV_SERVER"

#: The request file ``qgis-sdk dev`` writes for the QGIS process it starts; set
#: in every dev process, standalone or Desktop, which is what makes it the
#: marker of "a development session owns this QGIS" - ``qgis_sdk.console``
#: reads it to allow a plugin reload.
DEV_REQUEST_ENV: Final = "QGIS_SDK_DEV_REQUEST"

#: The ``qgis-sdk test`` target (``pure``, ``qgis``, ``desktop``) the pytest
#: plugin is running under; unset under a plain ``pytest``.
TEST_TARGET_ENV: Final = "QGIS_SDK_TEST_TARGET"


def dev_request(environ: os._Environ[str] | dict[str, str] | None = None) -> str | None:
    """The dev session's request file, or ``None`` outside ``qgis-sdk dev``."""
    source = os.environ if environ is None else environ
    return source.get(DEV_REQUEST_ENV) or None


def dev_server(environ: os._Environ[str] | dict[str, str] | None = None) -> str | None:
    """The dev-server origin, or ``None`` outside ``qgis-sdk dev``."""
    source = os.environ if environ is None else environ
    return source.get(DEV_SERVER_ENV) or None
