"""The open project: its CRS, its variables, its tree, its bookmarks, its file.

TASK-88 and decision-54 point 3. Before this slice the project service could
answer two questions - which layer ids it holds, and adding one - because the
reference workflow only needed to prove that an output reached the project after
a successful run (decision-19). Everything else was ``ctx.desktop``.

Five choices are deliberate.

*The tree is read and edited, never walked by the caller.*
:meth:`Project.layer_tree` answers a flat pre-order model with parent ids
(:class:`~qgis_sdk.models.project.LayerTree`), and :meth:`add_layer`,
:meth:`move_layer` and :meth:`remove_layer` name a group instead of handing out
a ``QgsLayerTreeGroup``. Every mutation answers with the tree it produced, so a
page never reads back to find out what its own call did.

*Adding is still separate from producing.* :meth:`add_layer` keeps the
decision-19 rule: nothing joins the project except through this call, after the
caller decided the work succeeded.

*Writing is explicit and staged.* :meth:`write` names a destination and honours
the export policy (no silent overwrite, no partial file), and :meth:`save`
refuses by name when the project has no file yet rather than prompting for one
from a worker thread.

*The change stream is a callback with a canceller*, the same shape the canvas
extent stream uses: a page subscribes, the host tells it what moved, and closing
the view cancels. Frames arrive in the order the project produced them.

*Destructiveness is declared where the host can read it.* ``remove_layer``,
``write``, ``save`` and ``read`` replace or discard project state, and the host
surface marks them so the agent consent list can ask (decision-54 point 2).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from qgis_sdk.models.canvas import CanvasExtent
from qgis_sdk.models.project import (
    Bookmark,
    LayerTree,
    ProjectChange,
    ProjectEntry,
    ProjectFile,
)

__all__ = ["Project", "ProjectChanged", "ProjectWatchCanceller"]

#: Cancels a project change subscription; idempotent, because a closing view
#: races the project all the time.
ProjectWatchCanceller = Callable[[], None]
ProjectChanged = Callable[[ProjectChange], None]


class Project(Protocol):
    """The open project, as a plugin and a page edit it.

    Implementations raise ``QgisSdkLayerNotFoundError`` for an unknown layer id,
    ``QgisSdkBookmarkNotFoundError`` for an unknown bookmark name,
    ``QgisSdkProjectFileError`` for a file that could not be read, written or
    saved, and ``QgisSdkUnsupportedCapabilityError`` on a host with no project at
    all (a QGIS Server has none - it draws a request).
    """

    def layer_ids(self) -> tuple[str, ...]:
        """Return the project's layer ids in tree order."""
        ...

    def add_layer(self, layer_id: str, *, group: str | None = None) -> LayerTree:
        """Add an owned layer to the project, optionally into a group.

        Adding the same layer twice leaves one entry (and moves it when
        ``group`` names a different group). An unknown group id is refused by
        name - ``QgisSdkLayerNotFoundError`` - and nothing is added.
        """
        ...

    def remove_layer(self, layer_id: str) -> LayerTree:
        """Remove one layer from the project; the layer itself stays open.

        Destructive: the project forgets the layer, so the *layer service* still
        owns it and ``Layers.get`` keeps answering. A layer the project does not
        hold is refused by name.
        """
        ...

    def move_layer(
        self, layer_id: str, *, group: str | None = None, index: int | None = None
    ) -> LayerTree:
        """Move one layer within the tree, into ``group`` and to ``index``.

        ``index`` is the position among the destination group's children; left
        out, the layer goes last. An index past the end is refused rather than
        clamped, because a clamp would silently place a layer somewhere else.
        """
        ...

    def set_visible(self, node_id: str, visible: bool) -> LayerTree:
        """Show or hide one layer or group and return the tree it produced.

        The node's own visibility, not its effective one: hiding a group hides
        what it holds without rewriting every child.
        """
        ...

    def layer_tree(self) -> LayerTree:
        """Return the whole tree: groups, layers, visibility and order."""
        ...

    def crs(self) -> str | None:
        """Return the project's CRS as an authority id, or ``None`` when unset."""
        ...

    def set_crs(self, auth_id: str) -> str:
        """Set the project's CRS and report the authority id it landed on.

        An identifier the host cannot resolve is refused with
        ``QgisSdkUnsupportedCapabilityError`` naming it; the project keeps its
        previous CRS.
        """
        ...

    def variables(self) -> tuple[ProjectEntry, ...]:
        """Return the project's expression variables, in the host's order."""
        ...

    def set_variable(self, name: str, value: str) -> tuple[ProjectEntry, ...]:
        """Set one project variable and return the variables it produced."""
        ...

    def unset_variable(self, name: str) -> tuple[ProjectEntry, ...]:
        """Remove one project variable; removing an absent one is a no-op."""
        ...

    def custom_properties(self) -> tuple[ProjectEntry, ...]:
        """Return the project's custom properties, in the host's order."""
        ...

    def set_custom_property(self, name: str, value: str) -> tuple[ProjectEntry, ...]:
        """Set one custom property and return the properties it produced."""
        ...

    def unset_custom_property(self, name: str) -> tuple[ProjectEntry, ...]:
        """Remove one custom property; removing an absent one is a no-op."""
        ...

    def bookmarks(self) -> tuple[Bookmark, ...]:
        """Return the project's bookmarks, in the host's order."""
        ...

    def add_bookmark(self, name: str, extent: CanvasExtent) -> tuple[Bookmark, ...]:
        """Add a bookmark (or replace the one with that name) and list them.

        A bookmark of the same name is replaced rather than duplicated: the name
        is the identity a page jumps by.
        """
        ...

    def remove_bookmark(self, name: str) -> tuple[Bookmark, ...]:
        """Remove one bookmark by name; an unknown name raises."""
        ...

    def bookmark(self, name: str) -> Bookmark:
        """Return one bookmark by name.

        Jumping *to* it is ``canvas.zoom_to(ZoomTarget.to_extent(...))`` rather
        than a second way to move the map: ``canvas.control`` is the one
        authority that moves the view, and a host with no canvas then has no
        bookmark call that silently does nothing. An unknown name raises
        ``QgisSdkBookmarkNotFoundError``.
        """
        ...

    def read(self, source: Path) -> LayerTree:
        """Replace the open project with the one in ``source``.

        Destructive: everything the project held is gone. The tree the file
        produced is the answer, so a caller does not have to ask again.
        """
        ...

    def write(self, destination: Path, *, overwrite: bool = False) -> ProjectFile:
        """Write the project to ``destination`` under the export policy.

        The destination is staged like an export: an existing file is replaced
        only with ``overwrite=True``, and a failure leaves the previous file
        untouched. The project's own file is *not* remembered by this call:
        writing a copy does not make it the file :meth:`save` writes, which is
        the file the project was opened from.
        """
        ...

    def save(self) -> ProjectFile:
        """Save the project to the file it was opened from.

        A project with no file yet - one this session never read or saved -
        refuses by name
        (``QgisSdkProjectFileError``) instead of opening a picker: choosing a
        destination is :meth:`write`'s job, and a host must not prompt from a
        handler it may run off the GUI thread.
        """
        ...

    def watch_changes(self, on_change: ProjectChanged) -> ProjectWatchCanceller:
        """Call ``on_change`` whenever the project changes, until cancelled."""
        ...
