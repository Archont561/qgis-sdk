from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    derive_title,
    register_describer,
    register_predicate_describer,
)
from qgis_sdk.declarations._describe import describe_lowered_plugin
from qgis_sdk.declarations._plugin import plugin

from ._plugin import (
    ActionRegistry,
    S,
    commit_inclusion,
    include_cycle_free,
    initial_plugin_fields,
    lowered_handler,
    register_declared_job,
    validate_handler,
    validate_metadata,
    validated_providers,
    validated_surfaces,
)

if TYPE_CHECKING:
    from qgis_sdk.declarations._descriptions import PluginDescription
    from qgis_sdk.providers import Provider
    from qgis_sdk.ui.surfaces import Surface


class _QgisSdkPluginMixin1:
    @property
    def surfaces(self) -> tuple[type[Surface], ...]:
        """The surfaces owned by this application."""
        return tuple(self._surfaces)

    @property
    def providers(self) -> tuple[Provider, ...]:
        """The Processing providers owned by this application."""
        return tuple(self._providers)

    @property
    def jobs(self) -> Any:
        """The named jobs an action reaches as ``ctx.jobs.<name>`` (TASK-116).

        ``None`` until the plugin declares some. Three spellings, one registry:
        a mapping (``app.jobs = {"add": add}``), a sequence of ``@job``
        functions (``app.jobs = (add, count_features)``), or the decorator
        (``@app.job()`` above the function). Each is validated at once, and the
        runtime builds the registry again from the result when the plugin
        starts.
        """
        if not self._declared_jobs:
            return self._jobs
        declared: dict[str, Callable[..., Any]] = {}
        if self._jobs is not None:
            from qgis_sdk.jobs import JobRegistry

            registry = JobRegistry.from_declaration(
                self._jobs, path=f"Plugin {self.id!r}"
            )
            declared = {name: registry.function(name) for name in registry.names}
        declared.update(self._declared_jobs)
        return declared

    @jobs.setter
    def jobs(self, declaration: Any) -> None:
        if declaration is not None:
            from qgis_sdk.jobs import JobRegistry

            registry = JobRegistry.from_declaration(
                declaration, path=f"Plugin {self.id!r}"
            )
            shared = sorted(set(registry.names) & set(self._declared_jobs))
            if shared:
                raise QgisSdkDeclarationError(
                    f"Plugin {self.id!r}: {shared[0]!r} is both assigned in `jobs` "
                    "and declared with @app.job; keep one declaration per name"
                )
        self._jobs = declaration

    def job(
        self,
        function: Callable[..., Any] | None = None,
        /,
        *,
        key: str | None = None,
        id: str | None = None,
        title: str | None = None,
    ) -> Any:
        """Declare one ``@job`` function as ``ctx.jobs.<name>``, decorator style.

        ``@app.job(id="demo.sum", title="Sum")`` and ``@app.job()`` both work;
        ``key=`` renames the entry the way a mapping key does. The name is the
        function's, snake_cased, exactly as a sequence entry of ``app.jobs``
        derives it. The function keeps its ``@job`` metadata - applied here
        when the author did not - so ``describe_job(add)`` works either way.
        """
        if function is None:
            return lambda target: self.job(target, key=key, id=id, title=title)
        return register_declared_job(self, function, key, id, title)

    def surface(self, surface: type[S]) -> type[S]:
        """Register a Dialog or Dock class without replacing it."""
        self.add_surface(surface)
        return surface

    def add_surface(self, surface: type[Surface]) -> None:
        from qgis_sdk.ui.surfaces import is_surface_class

        if not is_surface_class(surface):
            raise QgisSdkDeclarationError("surfaces must be Dialog/Dock subclasses")
        self._surfaces.append(surface)

    def add_provider(self, provider: Provider) -> None:
        self._providers.append(provider)

    def include(self, child: QgisSdkPlugin) -> None:
        """Snapshot another plugin's declarations into this plugin atomically."""
        members = include_cycle_free(self, child)
        surfaces = validated_surfaces(self, child)
        providers = validated_providers(self, child)
        jobs = _merge_jobs(self.jobs, child.jobs)
        self._extend(child._actions)
        self._surfaces = surfaces
        commit_inclusion(self, child, jobs, members, providers)

    def describe(self) -> PluginDescription:
        return describe_lowered_plugin(self._plugin_class())


class _QgisSdkPluginMixin2:
    def _plugin_class(self) -> type:
        """Lower the collected declarations into one SDK plugin class."""
        members: dict[str, Any] = {
            "surfaces": tuple(self._surfaces),
            "providers": tuple(self._providers),
        }
        if self.module is not None:
            members["__module__"] = self.module
        jobs = self.jobs
        if jobs is not None:
            members["jobs"] = jobs
        for id, title, function, events in self._actions:
            validate_handler(function, events, id)
            members[function.__name__] = lowered_handler(id, title, function, events)
        return plugin(id=self.id, title=self.title)(
            type("_ApplicationPlugin", (), members)
        )


class QgisSdkPlugin(_QgisSdkPluginMixin1, _QgisSdkPluginMixin2, ActionRegistry):
    """Collect functions explicitly and lower them to an SDK plugin class."""

    def __init__(self, *, id: str | None = None, title: str | None = None) -> None:
        try:
            module = sys._getframe(1).f_globals.get("__name__")
        except (AttributeError, ValueError):  # pragma: no cover - no frame to read
            module = None
        if id is None:
            if not isinstance(module, str) or module == "__main__":
                raise QgisSdkDeclarationError(
                    "cannot derive plugin id from the declaring module; pass id= explicitly"
                )
            id = module
        if title is None:
            if not isinstance(id, str):
                raise QgisSdkDeclarationError("id and title must be strings")
            parts = id.split(".")
            name = parts[-2] if len(parts) > 1 and parts[-1] == "plugin" else parts[-1]
            title = derive_title(name.replace("-", "_"))
        validate_metadata(id, title)
        super().__init__()
        self.id = id
        self.title = title
        #: The module that declared this application, kept because a host needs
        #: it for the paths a declaration names (a toolbar icon lives beside
        #: the plugin, not beside the runtime) - `qgis_sdk.app.run` fills it.
        self.module = module if isinstance(module, str) else None
        self._surfaces: list[type[Surface]] = []
        initial_plugin_fields(self)


def _describe_function(function):
    entry = function.__qgis_sdk_app_action__
    app = QgisSdkPlugin(id="application.description", title="Application description")
    app._actions = [entry]
    description = app.describe()
    return description.actions[0] if entry[3] is None else description.streams[0]


register_describer("__qgis_sdk_app_action__", _describe_function)
register_predicate_describer(
    lambda target: isinstance(target, QgisSdkPlugin), lambda app: app.describe()
)


def _merge_jobs(current: Any, incoming: Any) -> Any:
    """Combine two plugins' job declarations, refusing a shared name or id.

    Both sides are read through the same validation the runtime uses, so what
    ``include`` merges is exactly what the included plugin would have exposed -
    not a second, looser reading of the attribute.
    """
    if current is None:
        return incoming
    if incoming is None:
        return current
    from qgis_sdk.jobs import JobRegistry

    left = JobRegistry.from_declaration(current, path="the including plugin")
    right = JobRegistry.from_declaration(incoming, path="the included plugin")
    merged = {name: left.function(name) for name in left.names}
    ids = {description.id for description in left.descriptions()}
    for name in right.names:
        if name in merged:
            raise QgisSdkDeclarationError(f"duplicate job name {name!r}")
        description = right.description(name)
        if description.id in ids:
            raise QgisSdkDeclarationError(f"duplicate job id {description.id!r}")
        ids.add(description.id)
        merged[name] = right.function(name)
    return merged
