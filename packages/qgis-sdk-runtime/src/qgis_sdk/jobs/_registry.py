"""The plugin's declared job names, validated once at startup (decision-65).

A plugin names the jobs it exposes::

    jobs = {"add": add}          # explicit keys
    jobs = (add, count_features) # names derived from the function names

Either form builds the same :class:`JobRegistry`: a mapping from a name an
action writes as ``ctx.jobs.add.delay(...)`` to the ``@job`` function and its
validated description. Everything a submission could get wrong - a name that
cannot be read as an attribute, a name the service already uses, a function that
is not a ``@job``, two entries sharing a name, two entries sharing an id - is
refused here, when the plugin starts, and never while a job is being submitted.
Lookup afterwards is a dict read: no module is imported and nothing is scanned
on the way to a worker.
"""

from __future__ import annotations

import keyword
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any

from qgis_sdk.declarations import QgisSdkDeclarationError, derive_id
from qgis_sdk.jobs._authoring import _JOB_ATTRIBUTE, JobDescription, describe_job

__all__ = ["RESERVED_JOB_NAMES", "JobRegistry"]

#: Names a job may not take: they are what ``ctx.jobs`` itself reads, so a job
#: called ``after`` would shadow the way a job is ordered behind another. A
#: test keeps this in step with the public surface of ``Jobs`` and
#: ``JobService``.
RESERVED_JOB_NAMES: frozenset[str] = frozenset(
    {
        "active",
        "after",
        "bind",
        "delay",
        "describe",
        "faults",
        "jobs",
        "names",
        "parent",
        "plugin",
        "quiesce",
        "registry",
        "request_scoped",
        "resume",
        "scope",
        "scoped",
        "tick",
        "watch",
    }
)


class JobRegistry:
    """Names to ``@job`` declarations, built once from the plugin's declaration.

    ``path`` names the owner in every refusal - ``plugin 'field_tools'`` - so a
    message says which plugin declared the bad job. An empty registry is the
    normal state of a plugin that declares none: ``ctx.jobs`` still exists and
    refuses every name by listing what it has.
    """

    __slots__ = ("_entries", "_path")

    def __init__(
        self,
        entries: Mapping[str, tuple[Callable[..., Any], JobDescription]],
        path: str,
    ) -> None:
        self._entries = MappingProxyType(dict(entries))
        self._path = path

    @classmethod
    def empty(cls, path: str = "this plugin") -> JobRegistry:
        """A registry with no names; every lookup is refused by name."""
        return cls({}, path)

    @classmethod
    def from_declaration(cls, declaration: Any, *, path: str) -> JobRegistry:
        """Validate ``jobs = ...`` from a plugin class and index it by name.

        ``None`` (no declaration) gives an empty registry. A mapping keeps its
        keys; a sequence derives each name from the function's own name, the
        same snake_case rule ``@job`` uses for a bare id, without the module
        suffix that would make ``ctx.jobs.count_features_3f2a91`` the only way
        to reach a job.
        """
        if declaration is None:
            return cls.empty(path)
        if isinstance(declaration, Mapping):
            pairs = list(declaration.items())
        elif isinstance(declaration, Sequence) and not isinstance(
            declaration, str | bytes
        ):
            pairs = [(None, function) for function in declaration]
        else:
            raise QgisSdkDeclarationError(
                f"{path}: jobs must be a mapping of names to @job functions "
                f'(`jobs = {{"add": add}}`) or a sequence of @job functions '
                f"(`jobs = (add, count)`) - neither `{type(declaration).__name__}`"
            )
        entries: dict[str, tuple[Callable[..., Any], JobDescription]] = {}
        ids: dict[str, str] = {}
        for position, (given, function) in enumerate(pairs):
            name = _name_of(given, function, position, path)
            _refuse_reserved(name, path)
            description = _describe(name, given, function, position, path)
            if name in entries:
                raise QgisSdkDeclarationError(
                    f"{path}: two jobs are named {name!r}; give them explicit "
                    'keys (`jobs = {"first": one, "second": two}`)'
                )
            other = ids.get(description.id)
            if other is not None:
                raise QgisSdkDeclarationError(
                    f"{path}: jobs {other!r} and {name!r} declare the same id "
                    f"{description.id!r}; a job id has to stay unique across a "
                    "plugin's registry"
                )
            entries[name] = (function, description)
            ids[description.id] = name
        return cls(entries, path)

    # -- reading

    @property
    def path(self) -> str:
        """Who declared these jobs, for messages."""
        return self._path

    @property
    def names(self) -> tuple[str, ...]:
        """The declared names, in declaration order."""
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._entries

    def __iter__(self):
        return iter(self._entries)

    def function(self, name: str) -> Callable[..., Any]:
        """The ``@job`` function declared as ``name``."""
        return self._entry(name)[0]

    def description(self, name: str) -> JobDescription:
        """The validated description of ``name``."""
        return self._entry(name)[1]

    def descriptions(self) -> tuple[JobDescription, ...]:
        """Every declared description, in declaration order."""
        return tuple(description for _function, description in self._entries.values())

    def _entry(self, name: str) -> tuple[Callable[..., Any], JobDescription]:
        entry = self._entries.get(name)
        if entry is not None:
            return entry
        known = ", ".join(self._entries) or "none"
        raise AttributeError(
            f"{self._path} declares no job {name!r}; it declares: {known}"
        )

    def __repr__(self) -> str:
        return f"JobRegistry({self._path}, names={list(self._entries)})"


def _name_of(given: Any, function: Any, position: int, path: str) -> str:
    """The name a declaration entry is reached by, given or derived."""
    if given is None:
        name = getattr(function, "__name__", None)
        if not isinstance(name, str):
            raise QgisSdkDeclarationError(
                f"{path}: jobs[{position}] has no name to derive a job name from; "
                "give it an explicit key instead"
            )
        return derive_id(name)
    if not isinstance(given, str):
        raise QgisSdkDeclarationError(
            f"{path}: job names must be strings, not {type(given).__name__}"
        )
    if given.startswith("_") or not given.isidentifier() or keyword.iskeyword(given):
        raise QgisSdkDeclarationError(
            f"{path}: job name {given!r} must be a plain Python identifier, "
            f"because an action reaches it as `ctx.jobs.{given}`"
        )
    return given


def _refuse_reserved(name: str, path: str) -> None:
    if name in RESERVED_JOB_NAMES:
        raise QgisSdkDeclarationError(
            f"{path}: job name {name!r} is reserved by `ctx.jobs`; rename the "
            f'job or give it another key (`jobs = {{"{name}_job": {name}}}`)'
        )


def _describe(
    name: str, given: Any, function: Any, position: int, path: str
) -> JobDescription:
    """Validate one entry is a ``@job`` function and describe it now."""
    where = f"jobs[{name!r}]" if given is not None else f"jobs[{position}] ({name})"
    if not callable(function) or not hasattr(function, _JOB_ATTRIBUTE):
        raise QgisSdkDeclarationError(
            f"{path}: {where} is not a @job declaration; decorate the function "
            "with @job or drop it from the registry"
        )
    return describe_job(function)
