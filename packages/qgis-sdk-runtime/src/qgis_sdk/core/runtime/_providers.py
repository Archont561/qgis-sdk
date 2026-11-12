"""Provider declarations: what a lowered application class lists."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qgis_sdk.declarations import QgisSdkDeclarationError

if TYPE_CHECKING:
    from qgis_sdk.jobs import JobRegistry
    from qgis_sdk.providers import Provider

__all__ = ["declared_providers", "job_registry"]

_PROVIDERS_ATTRIBUTE = "providers"
"""Private attribute on a lowered application class."""


def declared_providers(plugin_class: type) -> tuple[Provider, ...]:
    """Return the providers a lowered application class lists, validated.

    ``providers`` is optional; when present it is a list or tuple of
    :class:`Provider` instances with distinct ids. Anything else is refused
    naming the class, so a typo (``providers = tools``) fails when the runtime
    is built rather than registering nothing in silence.

    The providers module imports this package, so the ``Provider`` check is
    deferred to construction time; the module is pure and always importable.
    """
    from qgis_sdk.providers import Provider

    listed = getattr(plugin_class, _PROVIDERS_ATTRIBUTE, None)
    if listed is None:
        return ()
    if not isinstance(listed, (list, tuple)) or not all(
        isinstance(provider, Provider) for provider in listed
    ):
        name = getattr(plugin_class, "__name__", repr(plugin_class))
        raise QgisSdkDeclarationError(
            f"{name}.{_PROVIDERS_ATTRIBUTE} must be a list of Provider instances"
        )
    _refuse_duplicate_provider_ids(plugin_class, listed)
    return tuple(listed)


def _refuse_duplicate_provider_ids(plugin_class: type, listed: list) -> None:
    """Refuse the same provider id twice, naming the class and the id."""
    name = getattr(plugin_class, "__name__", repr(plugin_class))
    seen: dict[str, object] = {}
    for provider in listed:
        if provider.id in seen:
            raise QgisSdkDeclarationError(
                f"{name}.{_PROVIDERS_ATTRIBUTE}: provider id {provider.id!r} is "
                "listed twice"
            )
        seen[provider.id] = provider


def job_registry(plugin_class: type, plugin_id: str) -> JobRegistry:
    """The plugin's ``jobs = ...`` declaration, validated (TASK-116).

    Read from the class the plugin actually runs - an intermediate author base
    counts too - and never from a module scan: what a plugin exposes is what it
    wrote down.
    """
    from qgis_sdk.jobs import JobRegistry

    for base in plugin_class.__mro__:
        if "jobs" in vars(base):
            return JobRegistry.from_declaration(
                vars(base)["jobs"], path=f"Plugin {plugin_id!r}"
            )
    return JobRegistry.empty(f"Plugin {plugin_id!r}")
