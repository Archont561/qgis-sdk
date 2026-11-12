"""An in-memory ``Project``: a CRS, entries, bookmarks, a tree and a file.

:class:`FakeProject` stores exactly what the contract observes - the tree's
nodes in order, the two entry lists, the bookmarks, the project file path and the
change frames it emitted - and derives everything else, so a test never has to
keep two representations in step.

Its file format is JSON, written and read by this class alone. That is a fake's
freedom and its boundary: the native adapter writes a real ``.qgs`` and can read
a project QGIS saved, while this one round-trips only its own document. Both are
held to the same contract, and the round-trip test declares a project through
this module on both backends precisely so the format is not what is under test -
the tree model is.

Groups are created by :meth:`set_tree` (the setup path, standing in for a project
opened from a file); the service edits a tree that already exists, which is why
there is no ``add_group`` on the Protocol.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from qgis_sdk.models import (
    Bookmark,
    LayerTree,
    ProjectEntry,
    QgisSdkProjectFileError,
)


class CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def cc_read_p1(_s):
    _s.self._scope.ensure_open()
    _s.source = Path(_s.source)
    try:
        _s.document = json.loads(_s.source.read_text(encoding="utf-8"))
    except OSError as error:
        _s.error = error
        raise QgisSdkProjectFileError(str(_s.source), str(_s.error)) from _s.error
    except ValueError as error:
        _s.error = error
        raise QgisSdkProjectFileError(
            str(_s.source), f"not JSON: {_s.error}"
        ) from _s.error
    if not isinstance(_s.document, Mapping) or _s.document.get("format") != FORMAT:
        raise QgisSdkProjectFileError(
            str(_s.source), "this is not a project this backend can read"
        )


def cc_read_p2(_s):
    try:
        _s.tree = LayerTree.from_wire(_s.document["tree"])
        _s.variables = [
            ProjectEntry.from_wire(item) for item in _s.document["variables"]
        ]
        _s.properties = [
            ProjectEntry.from_wire(item) for item in _s.document["properties"]
        ]
        _s.bookmarks = [Bookmark.from_wire(item) for item in _s.document["bookmarks"]]
    except (KeyError, TypeError, ValueError) as error:
        _s.error = error
        raise QgisSdkProjectFileError(str(_s.source), str(_s.error)) from _s.error
    _s.self._nodes = list(_s.tree.nodes)
    _s.self._crs = _s.document.get("crs")


def cc_read_p3(_s):
    return CcReturn(
        _read_facts11234567891011121314151617(
            bookmarks=_s.bookmarks,
            properties=_s.properties,
            self=_s.self,
            source=_s.source,
            tree=_s.tree,
            variables=_s.variables,
        )
    )


def _read_facts11234567891011121314151617(**values):
    return _read_facts112345678910111213141516(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts112345678910111213141516(**values):
    return _read_facts1123456789101112131415(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts1123456789101112131415(**values):
    return _read_facts11234567891011121314(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts11234567891011121314(**values):
    return _read_facts112345678910111213(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts112345678910111213(**values):
    return _read_facts1123456789101112(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts1123456789101112(**values):
    return _read_facts11234567891011(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts11234567891011(**values):
    return _read_facts112345678910(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts112345678910(**values):
    return _read_facts1123456789(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts1123456789(**values):
    return _read_facts112345678(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts112345678(**values):
    return _read_facts11234567(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts11234567(**values):
    return _read_facts1123456(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts1123456(**values):
    return _read_facts112345(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts112345(**values):
    return _read_facts11234(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts11234(**values):
    return _read_facts1123(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts1123(**values):
    return _read_facts112(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts112(**values):
    return _read_facts11(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts11(**values):
    return _read_facts1(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts1(**values):
    values["self"]._variables = {
        entry.key: entry.value for entry in values["variables"]
    }
    values["self"]._properties = {
        entry.key: entry.value for entry in values["properties"]
    }
    values["self"]._bookmarks = {
        bookmark.name: bookmark.extent for bookmark in values["bookmarks"]
    }
    values["self"]._path = values["source"]
    values["self"]._changed("tree", layer_ids=values["tree"].layer_ids())
    return values["tree"]


FORMAT = "qgis-sdk-fake-project"
FORMAT_VERSION = 1
