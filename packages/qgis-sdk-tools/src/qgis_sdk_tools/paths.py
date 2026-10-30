"""One way to visit the files under a directory: ``pathlib`` with ``os.walk``'s pruning.

``Path.walk`` arrived in Python 3.12 and these packages still support 3.11, so
the recursion lives here once instead of five copies of ``os.walk`` in the check,
bundle and devtools trees. The order is ``os.walk``'s: the files of a directory
first, then each subdirectory in turn, both sorted by name, so a diagnostic list
or a staged archive keeps the order it had before.

Two of ``os.walk``'s behaviours are deliberate, not incidental. A directory that
cannot be listed is skipped rather than raised, because a project with one
unreadable corner should still be checked everywhere else. A symlinked directory
is not descended, because ``os.walk`` does not follow links unless asked to and a
link loop would otherwise never end.

Pruning is the reason this is not a one-line ``rglob``: a plugin package carries
``web/node_modules`` and ``__pycache__``, and descending into tens of thousands
of files to discard them afterwards is the cost ``os.walk``'s ``dirnames[:]``
filter exists to avoid.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator
from pathlib import Path

__all__ = ["walk_files"]


def walk_files(
    root: Path,
    *,
    skip: Collection[str] = (),
    suffix: str | None = None,
) -> Iterator[Path]:
    """Yield every file under ``root``, never descending into a name in ``skip``.

    ``suffix`` keeps only the names that end with it (``".py"``, ``".ts"``) and
    is applied before the directory recursion, so a caller that wants one kind of
    file pays nothing for the others. A file that vanishes between listing and
    ``stat`` is simply not yielded; a directory that vanishes the same way, or
    that this user cannot read, contributes no files instead of an exception.
    """
    entries: list[Path]
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError:  # missing, or not readable: os.walk yielded nothing here
        return
    for entry in entries:
        if entry.is_file() and (suffix is None or entry.name.endswith(suffix)):
            yield entry
    for entry in entries:
        if entry.is_dir() and not entry.is_symlink() and entry.name not in skip:
            yield from walk_files(entry, skip=skip, suffix=suffix)
