"""The ``qgis-sdk`` command line: argument parsing over the public API, nothing else.

This module is what the wheel's ``qgis-sdk`` console script points at, and
``python -m qgis_sdk_tools`` reaches the same :func:`main`, so a pip or
``pixi add --pypi`` install gets the command without an activated environment. It is
the one executable-shaped file inside ``src/qgis_sdk`` and it is there for that
reason: unlike the automation tools in ``packages/qgis-sdk-python/scripts``, which are
development-only and are not part of either distribution, generating a project is a
library operation with no display, no QGIS and no Qt, so shipping it is the point.

All behaviour lives in :mod:`qgis_sdk_tools.scaffold`, :mod:`qgis_sdk_tools.check` and
:mod:`qgis_sdk_tools.generate`, so callers that do not want a shell reach the
same API directly. A command that reads or writes anything beyond its
arguments receives a :class:`qgis_sdk_tools.cli.CliRuntime` through ``ctx.obj``
(decision-34): the shell gets the process, a test passes its own.
"""

from __future__ import annotations

from qgis_sdk_tools._commands import app, main

__all__ = ["app", "main"]

if __name__ == "__main__":
    main()
