"""The grant vocabulary as one table: client × host operation (decision-54).

An operation is always ``<service>.<operation>``, and the name that selects it is
always one of :func:`qgis_sdk.bridge.host.host_grant_names`. Two clients speak
that vocabulary - the page through ``[tool.qgis-sdk.web] grants`` and the
console through ``[tool.qgis-sdk.console] grants`` - so this module prints them
side by side, which is what makes a typo in one section visible before it
narrows a surface in silence.

The third client is shown for the same reason: the plugin HTTP API's allowlist
(``PluginHttpServer(actions=...)``) is authority too, and it names **actions and
streams**, not host operations. Printing it beside the other two is how the
vocabulary stays honest about which client can name what - the agent dialect
decision-54 originally listed was withdrawn with decision-49.

Nothing here reads a project from disk or imports the plugin: the input is the
validated :class:`~qgis_sdk_tools.project.ProjectConfig`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from qgis_sdk.bridge.host import (
    HOST_OPERATIONS,
    granted_operations,
    host_grant_names,
    host_operation_ids,
)

from qgis_sdk_tools.project import ProjectConfig

#: One line per client: what declares its authority, and what vocabulary it names.
CLIENTS: Final = (
    (
        "page",
        "[tool.qgis-sdk.web] grants",
        "host grants or operation ids",
    ),
    (
        "console",
        "[tool.qgis-sdk.console] grants",
        "host grants or operation ids (unset: every operation)",
    ),
    (
        "http",
        "PluginHttpServer(actions=...)",
        "plugin action and stream ids, not host operations",
    ),
)


@dataclass(frozen=True, slots=True)
class GrantRow:
    """One host operation, the grant that selects it, and who reaches it."""

    operation: str
    grant: str
    page: bool
    console: bool


@dataclass(frozen=True, slots=True)
class GrantsMatrix:
    """Client × operation authority for one project (decision-54 point 2)."""

    #: Whether the project declares a page at all; without one nothing reaches it.
    page_declared: bool
    #: Whether the console keeps its default, every operation.
    console_unrestricted: bool
    rows: tuple[GrantRow, ...]

    def granted(self, client: str) -> tuple[str, ...]:
        """The operation ids ``client`` may reach, in catalogue order."""
        if client == "page":
            return tuple(row.operation for row in self.rows if row.page)
        if client == "console":
            return tuple(row.operation for row in self.rows if row.console)
        raise KeyError(client)

    def render(self) -> str:
        """Print the clients and the matrix as plain text, widest field first."""
        client_width = max(len("client"), *(len(name) for name, _, _ in CLIENTS))
        declares_width = max(len("declares"), *(len(d) for _, d, _ in CLIENTS))
        operation_width = max(len("operation"), *(len(r.operation) for r in self.rows))
        grant_width = max(len("grant"), *(len(r.grant) for r in self.rows))
        lines = [
            "grants: one vocabulary, one name per operation",
            "",
            f"{'client':<{client_width}}  {'declares':<{declares_width}}  names",
        ]
        for name, declares, names in CLIENTS:
            lines.append(
                f"{name:<{client_width}}  {declares:<{declares_width}}  {names}"
            )
        if not self.page_declared:
            lines.append("")
            lines.append(
                "no [tool.qgis-sdk.web] is declared, so no page reaches anything"
            )
        page_width = max(len("page"), len("granted"), len("none"))
        console_width = max(len("console"), len("granted"))
        lines += [
            "",
            (
                f"{'operation':<{operation_width}}  {'grant':<{grant_width}}  "
                f"{'page':<{page_width}}  {'console':<{console_width}}"
            ),
        ]
        for row in self.rows:
            page = _mark(row.page, declared=self.page_declared)
            console = "granted" if row.console else "-"
            lines.append(
                f"{row.operation:<{operation_width}}  {row.grant:<{grant_width}}  "
                f"{page:<{page_width}}  {console:<{console_width}}"
            )
        return "\n".join(lines)


def _mark(granted: bool, *, declared: bool) -> str:
    """A page cell: ``granted``, ``-``, or ``no page`` when nothing is declared."""
    if granted:
        return "granted"
    return "-" if declared else "none"


def _selected(grants: tuple[str, ...]) -> tuple[str, ...]:
    """The ids ``grants`` selects, skipping names validation already reported.

    :func:`granted_operations` raises on an unknown entry, which is right for a
    runtime that is about to narrow a surface. Here the report has already
    printed the ``GRANT001`` finding, and the matrix is what the author reads
    next, so an unknown name is dropped rather than raised a second time.
    """
    known = set(host_grant_names()) | set(host_operation_ids())
    return granted_operations(tuple(entry for entry in grants if entry in known))


def grants_matrix(config: ProjectConfig) -> GrantsMatrix:
    """Build the matrix for ``config``: what each client reaches, operation by operation."""
    page = _selected(config.web.grants) if config.web is not None else ()
    console = (
        host_operation_ids()
        if config.console.unrestricted
        else _selected(config.console.grants)
    )
    page_ids = set(page)
    console_ids = set(console)
    return GrantsMatrix(
        page_declared=config.web is not None,
        console_unrestricted=config.console.unrestricted,
        rows=tuple(
            GrantRow(
                operation=operation.id,
                grant=operation.grant,
                page=config.web is not None and operation.id in page_ids,
                console=operation.id in console_ids,
            )
            for operation in HOST_OPERATIONS
        ),
    )
