"""Read every deprecation mark out of the SDK this interpreter has installed.

The marks live on the symbols themselves (``qgis_sdk.deprecation``), so the
table is read from the installed package rather than from a list beside it: a
mark that was added in this release is visible to ``check`` in the same release,
without a second place to update.

The public modules come from the inventory's module list, which is the same list
`qgis-sdk api dump` walks - one definition of "public", two readers.
"""

from __future__ import annotations

from importlib import import_module

from qgis_sdk.deprecation import Deprecation, deprecation_of

from qgis_sdk_tools.api import PUBLIC_MODULES

__all__ = ["Marks", "deprecated_names"]

Marks = dict[tuple[str, str], Deprecation]
"""Every deprecated name in the installed SDK, keyed by module and name."""


def deprecated_names() -> Marks:
    """Every deprecated public name, keyed by ``(module, name)``."""
    found: Marks = {}
    for module_name in PUBLIC_MODULES:
        module = import_module(module_name)
        for exported in getattr(module, "__all__", ()):
            mark = deprecation_of(getattr(module, exported, None))
            if mark is not None:
                found[(module_name, exported)] = mark
    return found
