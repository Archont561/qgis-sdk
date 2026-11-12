from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ._build import (
    read_kit_pins,
    read_package_json_version,
    read_pyproject_version,
    read_recipe_context,
    read_recipe_version,
    runtime_range_includes,
)
from ._history import (
    ALIAS_DEPENDENCY,
    UI_ALIAS_DEPENDENCY,
    UI_PEER,
    QgisSdkReleaseError,
    QgisSdkReleaseVersionError,
)
from ._version import Version, normalize_scope


def read_alias_versions(
    text: str, dependency: str = ALIAS_DEPENDENCY
) -> tuple[Version, Version]:
    """Return ``(alias version, pinned bridge version)`` from the alias manifest.

    The pin has to be an exact version: ``Version.parse`` refuses ranges, which
    is the point.
    """
    data = json.loads(text)
    dependencies = data.get("dependencies")
    if not isinstance(dependencies, dict) or dependency not in dependencies:
        raise QgisSdkReleaseError(f"alias package.json does not depend on {dependency}")
    return (
        Version.parse(str(data["version"])),
        Version.parse(str(dependencies[dependency])),
    )


_PEER_RANGE = re.compile(r"^>=\s*(?P<lower>\S+)\s+<\s*(?P<upper>\S+)$")


def read_ui_peer_range(text: str) -> tuple[Version, str]:
    """Return ``(lower, upper)`` of the UI package's peer range on the bridge.

    The range is written ``>=X.Y.Z <U``: a floor the components were built
    against and an exclusive ceiling, the npm spelling of the minor window the
    tools declare on the runtime.
    """
    data = json.loads(text)
    peers = data.get("peerDependencies") or {}
    raw = peers.get(UI_PEER)
    if not isinstance(raw, str):
        raise QgisSdkReleaseError(
            f"ui package.json names no peerDependencies entry for {UI_PEER}"
        )
    match = _PEER_RANGE.match(raw.strip())
    if match is None:
        raise QgisSdkReleaseVersionError(
            f"the ui peer range on {UI_PEER} must read '>=X.Y.Z <U', got {raw!r}"
        )
    return Version.parse(match.group("lower")), match.group("upper")


def ui_peer_range_includes(peer: tuple[Version, str], bridge: Version) -> bool:
    """Whether the bridge at HEAD falls inside the UI package's peer range."""
    lower, upper = peer
    return runtime_range_includes(lower, upper, bridge)


_SCAFFOLD_PIN = re.compile(r'^(SDK_NPM_VERSION: Final = ")([^"\n]*)(")$', re.MULTILINE)


def read_scaffold_pin(text: str) -> Version:
    """Return the bridge version ``qgis-sdk new`` pins in ``scaffold/web/_plan.py``.

    An exact version: ``Version.parse`` refuses a range, which is the point of
    a controlled template.
    """
    match = _SCAFFOLD_PIN.search(text)
    if match is None:
        raise QgisSdkReleaseError(
            "scaffold/web/_plan.py declares no SDK_NPM_VERSION pin"
        )
    return Version.parse(match.group(2))


def stamp_scaffold_pin(text: str, version: Version) -> str:
    """Move the scaffold's bridge pin to ``version``, touching nothing else."""
    if _SCAFFOLD_PIN.search(text) is None:
        raise QgisSdkReleaseError(
            "scaffold/web/_plan.py declares no SDK_NPM_VERSION pin"
        )
    return _SCAFFOLD_PIN.sub(rf"\g<1>{version}\g<3>", text, count=1)


_SCAFFOLD_UI_PIN = re.compile(
    r'^(UI_NPM_VERSION: Final = ")([^"\n]*)(")$', re.MULTILINE
)


def has_scaffold_ui_pin(text: str) -> bool:
    """Whether ``scaffold/web/_plan.py`` pins the web components at all."""
    return _SCAFFOLD_UI_PIN.search(text) is not None


def read_scaffold_ui_pin(text: str) -> Version:
    """Return the components version ``qgis-sdk new --ui-dependency`` pins.

    Exact like the bridge pin: the templates import one published version.
    """
    match = _SCAFFOLD_UI_PIN.search(text)
    if match is None:
        raise QgisSdkReleaseError(
            "scaffold/web/_plan.py declares no UI_NPM_VERSION pin"
        )
    return Version.parse(match.group(2))


def stamp_scaffold_ui_pin(text: str, version: Version) -> str:
    """Move the scaffold's components pin to ``version``, touching nothing else."""
    if not has_scaffold_ui_pin(text):
        raise QgisSdkReleaseError(
            "scaffold/web/_plan.py declares no UI_NPM_VERSION pin"
        )
    return _SCAFFOLD_UI_PIN.sub(rf"\g<1>{version}\g<3>", text, count=1)


@dataclass(frozen=True)
class ManifestVersions:
    """The version each released manifest currently carries."""

    pyproject: Version
    package_json: Version
    recipe: Version | None = None
    alias: Version | None = None
    alias_dependency: Version | None = None
    runtime: Version | None = None
    tools: Version | None = None
    kit_pins: tuple[tuple[str, Version], ...] = ()
    recipe_runtime: Version | None = None
    recipe_tools: Version | None = None
    scaffold_pin: Version | None = None
    ui: Version | None = None
    ui_peer_range: tuple[Version, str] | None = None
    ui_alias: Version | None = None
    ui_alias_dependency: Version | None = None
    scaffold_ui_pin: Version | None = None

    def items(self) -> tuple[tuple[str, Version], ...]:
        """Return the labelled versions that exist, in reporting order.

        The UI package is not among them: it versions on its own train and
        never has to agree with the kit or the bridge (see :meth:`ui_items`).
        """
        found = [
            ("pyproject.toml", self.pyproject),
            ("package.json", self.package_json),
        ]
        if self.runtime is not None:
            found.append(("runtime pyproject.toml", self.runtime))
        if self.tools is not None:
            found.append(("tools pyproject.toml", self.tools))
        for requirement, pinned in self.kit_pins:
            found.append((f"kit pin {requirement}", pinned))
        if self.recipe is not None:
            found.append(("recipe.yaml", self.recipe))
        if self.recipe_runtime is not None:
            found.append(("recipe runtime_version", self.recipe_runtime))
        if self.recipe_tools is not None:
            found.append(("recipe tools_version", self.recipe_tools))
        if self.alias is not None:
            found.append(("alias package.json", self.alias))
        if self.alias_dependency is not None:
            found.append(("alias dependency", self.alias_dependency))
        if self.scaffold_pin is not None:
            found.append(("scaffold pin", self.scaffold_pin))
        return tuple(found)

    def ui_items(self) -> tuple[tuple[str, Version], ...]:
        """The manifests of the ``ui`` scope, when the package is present.

        The components' package.json leads; the unscoped alias (its version
        and its exact pin) and the scaffold's ``UI_NPM_VERSION`` follow it,
        so a release that forgot one of them is named here.
        """
        if self.ui is None:
            return ()
        found = [("ui package.json", self.ui)]
        if self.ui_alias is not None:
            found.append(("ui alias package.json", self.ui_alias))
        if self.ui_alias_dependency is not None:
            found.append(("ui alias dependency", self.ui_alias_dependency))
        if self.scaffold_ui_pin is not None:
            found.append(("scaffold ui pin", self.scaffold_ui_pin))
        return tuple(found)

    def agreed(self) -> Version:
        """Return the version every manifest carries, or name the disagreement.

        Manifests only have to agree *within* a release scope: ``pyproject.toml``
        and ``recipe.yaml`` ship the Python package, ``package.json`` ships the
        bridge, and the two packages version independently.
        """
        from ._contracts import require_one_version

        return require_one_version(self.items())

    def to_json(self) -> dict:
        """Serialize the versions for diagnostics."""
        return {name: str(version) for name, version in self.items()}


@dataclass(frozen=True, slots=True)
class ManifestSources:
    """The manifest texts a release reads, grouped by what they version."""

    pyproject_text: str
    package_text: str
    recipe_text: str | None = None
    alias_text: str | None = None
    runtime_text: str | None = None
    tools_text: str | None = None
    scaffold_text: str | None = None
    ui_text: str | None = None
    ui_alias_text: str | None = None


def _alias_pair(text: str | None, dependency: str | None = None):
    """The version and dependency an alias package declares, if it exists."""
    if text is None:
        return None, None
    if dependency is None:
        return read_alias_versions(text)
    return read_alias_versions(text, dependency=dependency)


def _kit_fields(sources: ManifestSources) -> dict:
    """The kit, bridge, recipe and alias versions."""
    alias, alias_dependency = _alias_pair(sources.alias_text)
    recipe = sources.recipe_text
    return {
        "pyproject": read_pyproject_version(sources.pyproject_text),
        "package_json": read_package_json_version(sources.package_text),
        "recipe": read_recipe_version(recipe) if recipe is not None else None,
        "alias": alias,
        "alias_dependency": alias_dependency,
        "recipe_runtime": (
            read_recipe_context(recipe, "runtime_version")
            if recipe is not None
            else None
        ),
        "recipe_tools": (
            read_recipe_context(recipe, "tools_version") if recipe is not None else None
        ),
    }


def _python_fields(sources: ManifestSources) -> dict:
    """The runtime and tools versions, and the kit's pins on them."""
    split = bool(sources.runtime_text or sources.tools_text)
    return {
        "runtime": (
            read_pyproject_version(sources.runtime_text)
            if sources.runtime_text
            else None
        ),
        "tools": (
            read_pyproject_version(sources.tools_text) if sources.tools_text else None
        ),
        "kit_pins": read_kit_pins(sources.pyproject_text) if split else (),
    }


def _typescript_fields(sources: ManifestSources) -> dict:
    """The bridge pin the scaffold offers to generated projects."""
    scaffold = sources.scaffold_text
    return {
        "scaffold_pin": (read_scaffold_pin(scaffold) if scaffold is not None else None)
    }


def _ui_fields(sources: ManifestSources) -> dict:
    """The web components' version, peer range, alias and scaffold pin."""
    ui_alias, ui_alias_dependency = _alias_pair(
        sources.ui_alias_text, UI_ALIAS_DEPENDENCY
    )
    ui, scaffold = sources.ui_text, sources.scaffold_text
    return {
        "ui": read_package_json_version(ui) if ui is not None else None,
        "ui_peer_range": read_ui_peer_range(ui) if ui is not None else None,
        "ui_alias": ui_alias,
        "ui_alias_dependency": ui_alias_dependency,
        "scaffold_ui_pin": (
            read_scaffold_ui_pin(scaffold)
            if scaffold is not None and has_scaffold_ui_pin(scaffold)
            else None
        ),
    }


def manifest_versions(sources: ManifestSources) -> ManifestVersions:
    """Read all released manifests and return what each one carries.

    ``pyproject_text`` is the kit's; when the runtime's and the tools' are given
    too, their versions and the kit's pins on them join the Python scope.
    ``scaffold_text`` is ``scaffold/web/_plan.py``, whose bridge pin joins the
    TypeScript scope and whose components pin (when it has one) joins the
    ``ui`` scope. ``ui_text`` is the web components' package.json: its
    version and its peer range on the bridge form the ``ui`` scope, with
    ``ui_alias_text`` (the unscoped alias) when it is given.
    """
    return ManifestVersions(
        **_kit_fields(sources),
        **_python_fields(sources),
        **_typescript_fields(sources),
        **_ui_fields(sources),
    )


_KIT_MANIFESTS = ("pyproject.toml", "recipe.yaml")
_RUNTIME_MANIFESTS = ("runtime pyproject.toml", "recipe runtime_version")
_TOOLS_MANIFESTS = ("tools pyproject.toml", "recipe tools_version")
_KIT_PIN_MANIFESTS = (
    "kit pin qgis-sdk-runtime",
    "kit pin qgis-sdk-tools",
)
_PYTHON_MANIFESTS = (
    *_KIT_MANIFESTS,
    *_RUNTIME_MANIFESTS,
    *_TOOLS_MANIFESTS,
    *_KIT_PIN_MANIFESTS,
)
_MANIFEST_GROUPS = {
    "python": _PYTHON_MANIFESTS,
    "runtime": _RUNTIME_MANIFESTS,
    "tools": _TOOLS_MANIFESTS,
    "kit": _KIT_MANIFESTS,
}
_TYPESCRIPT_MANIFESTS = (
    "package.json",
    "alias package.json",
    "alias dependency",
    "scaffold pin",
)


def scoped_manifest_versions(
    versions: ManifestVersions, scope: str
) -> tuple[tuple[str, Version], ...]:
    """Return only the manifests a release scope is allowed to stamp.

    The Python package owns ``pyproject.toml`` and the conda ``recipe.yaml``;
    the bridge owns ``package.json``. An unscoped ``v*`` release owns all three,
    which is what an alignment release is. The ``ui`` scope owns the web
    components' package.json alone.
    """
    wanted = scope if scope == "kit" else normalize_scope(scope)
    if wanted == "all":
        return versions.items()
    if wanted == "ui":
        return versions.ui_items()
    allowed = _MANIFEST_GROUPS.get(wanted, _TYPESCRIPT_MANIFESTS)
    return tuple(
        (name, version) for name, version in versions.items() if name in allowed
    )
