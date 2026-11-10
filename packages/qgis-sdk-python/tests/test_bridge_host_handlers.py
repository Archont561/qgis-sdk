"""The handler table: one module per namespace, one handler per declared id.

The registration reads ``HANDLERS`` and nothing else, so a module left out of the
merge would register a surface with holes in it and a duplicate key would shadow
the handler it overwrote - both silently. These tests are the shape check that
keeps the table honest; ``test_bridge_host.py`` is the behaviour check.
"""

from __future__ import annotations

from qgis_sdk.bridge.host._operations import HOST_OPERATIONS
from qgis_sdk.bridge.host.handlers import HANDLERS

MODULES = (
    "qgis_sdk.bridge.host.handlers._algorithms",
    "qgis_sdk.bridge.host.handlers._canvas",
    "qgis_sdk.bridge.host.handlers._connections",
    "qgis_sdk.bridge.host.handlers._features",
    "qgis_sdk.bridge.host.handlers._layers",
    "qgis_sdk.bridge.host.handlers._network",
    "qgis_sdk.bridge.host.handlers._project",
    "qgis_sdk.bridge.host.handlers._styles",
)
"""Every module the merge reads, in the order the merge names them."""


def declared_ids() -> set[str]:
    """The ids the operation table declares; those are the ids that must answer."""
    return {operation.id for operation in HOST_OPERATIONS}


def test_every_declared_operation_has_exactly_one_handler() -> None:
    assert set(HANDLERS) == declared_ids()


def test_no_handler_module_shadows_another() -> None:
    """A duplicate id would be answered by whichever module the merge named last."""
    merged = sum(len(handler_module.HANDLERS) for _, handler_module in _loaded())
    assert merged == len(HANDLERS)


def test_each_namespace_is_answered_by_one_module() -> None:
    """A prefix belongs to one module, so a handler never lands in two places."""
    prefixes: dict[str, str] = {}
    for module_name, handler_module in _loaded():
        for operation_id in handler_module.HANDLERS:
            prefix = operation_id.split(".")[0]
            owner = prefixes.setdefault(prefix, module_name)
            assert owner == module_name, (
                f"{prefix} answered by {owner} and {module_name}"
            )


def _loaded() -> list[tuple[str, object]]:
    """Import each handler module by name, so the table is read as the merge reads it."""
    return [(name, __import__(name, fromlist=["HANDLERS"])) for name in MODULES]
