from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from qgis_sdk.bridge.protocol import HOST_SCHEMA_VERSION
from qgis_sdk.models.errors import QgisSdkBridgeError

from ._operations import HOST_OPERATIONS

_NOTIFICATION_LEVELS_DEFERRED = (
    "a level on the message bar; `notifications.info` stays the one wire operation "
    "until a later protocol version adds levelled feedback without moving "
    "HOST_FINGERPRINT in the middle of a release train"
)
DEFERRED_HOST_METHODS: Mapping[str, str] = {
    "Layers.selection": (
        "returns every selected feature id; unbounded, and needs the paging the "
        "protocol does not have for it yet"
    ),
    "Rasters.export_raster": (
        "writes a whole raster, which is minutes of work on a real dataset; a "
        "page asks its plugin action, which runs it as a @job on a worker and "
        "hands the file back as a ref (the layouts precedent, decision-54 point 3)"
    ),
    "Layers.export_vector": (
        "takes a filesystem destination, which a page never supplies (decision-20); "
        "a page exports through `files.export` and a host-minted write ref, and a "
        "plugin action resolves a bare file name against a host-chosen directory "
        "(the reference plugin's `export_layer`)"
    ),
    "Layouts.export": (
        "submits the render as a job and answers its handle; a page has no "
        "job-status operation to follow one with, so `layouts.export` runs the "
        "same render in the request that asked for it and answers the file"
    ),
    "Layouts.run_atlas": (
        "the job form of `layouts.atlas`: one task in the plugin's task bar. A "
        "page's run is the request itself, which ends with one ref per page"
    ),
    "Settings.set": "mutates persisted state; arrives with the mutation slice",
    "EditingSession.close": (
        "a session ends with the view that began it, so the dispatcher closes it "
        "on dispose and a page never closes a session a later message names"
    ),
    "Notifications.success": _NOTIFICATION_LEVELS_DEFERRED,
    "Notifications.warning": _NOTIFICATION_LEVELS_DEFERRED,
    "Notifications.critical": _NOTIFICATION_LEVELS_DEFERRED,
    "Notifications.with_action": (
        "attaches a button that runs a plugin action; a page draws its own "
        "buttons over `actions.call` (decision-55), and a host-side button a page "
        "can press needs a later protocol version to carry it"
    ),
    "Algorithms.execute": (
        "the plugin-local provider surface; a page runs any algorithm, the "
        "plugin's own included, through `algorithms.run` (decision-64)"
    ),
}


def host_grants() -> dict[str, str]:
    """Return the canonical grant each operation needs, keyed by operation id."""
    return {operation.id: operation.grant for operation in HOST_OPERATIONS}


def host_grant_names() -> tuple[str, ...]:
    """Return the canonical grant names, sorted: the one vocabulary (decision-54).

    Every client that names authority reads this list - the page's
    ``[tool.qgis-sdk.web] grants``, the console's
    ``[tool.qgis-sdk.console] grants``, the manifest, the coverage map and the
    ``GRANT001`` finding - so a name cannot be a grant for one client and a typo
    for another.
    """
    return tuple(sorted({operation.grant for operation in HOST_OPERATIONS}))


def host_operation_ids() -> tuple[str, ...]:
    """Return every declared operation id, in catalogue order."""
    return tuple(operation.id for operation in HOST_OPERATIONS)


def granted_operations(grants: Sequence[str]) -> tuple[str, ...]:
    """Return the operation ids a project's ``grants`` list selects (decision-43).

    Each entry is either a grant (``layers.read`` selects every operation
    that needs it) or one operation id (``project.layer_ids``). The result
    keeps the catalogue's order without duplicates - what ``only=`` of
    :func:`register_host_operations` expects. An entry that is neither is a
    typo that would otherwise narrow the surface in silence, so it raises.
    """
    wanted = set(grants)
    operation_ids = host_operation_ids()
    known = set(operation_ids) | set(host_grant_names())
    for entry in grants:
        if entry not in known:
            raise QgisSdkBridgeError(
                f"unknown host grant {entry!r}; grants are "
                f"{', '.join(host_grant_names())} and "
                f"operation ids are {', '.join(operation_ids)}"
            )
    return tuple(
        operation.id
        for operation in HOST_OPERATIONS
        if operation.id in wanted or operation.grant in wanted
    )


def host_description() -> dict[str, Any]:
    """Return the manifest as the description shape the generator renders."""
    return {
        "schema_version": HOST_SCHEMA_VERSION,
        "id": "qgis.host",
        "title": "QGIS host services",
        "actions": [
            operation.to_description()
            for operation in HOST_OPERATIONS
            if operation.events is None
        ],
        "streams": [
            operation.to_description()
            for operation in HOST_OPERATIONS
            if operation.events is not None
        ],
    }
