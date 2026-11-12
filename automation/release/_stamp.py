from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
from pathlib import Path

from ._build import (
    TOOLS_RUNTIME_RANGE,
    compute_plan,
    example_label,
    example_window_includes,
    minor_window,
    next_minor,
    read_example_windows,
    read_pyproject_version,
    read_tools_runtime_range,
    runtime_range_includes,
    stamp_alias_package_json,
    stamp_example_windows,
    stamp_kit_pins,
    stamp_package_json,
    stamp_pyproject,
    stamp_recipe,
    stamp_recipe_context,
    stamp_tools_runtime_range,
)
from ._changelog import parse_versionrc
from ._contracts import (
    cli_plan_scope,
    commits_since,
    emit_plan,
    plan_options,
    requested_scope,
    resolve_dry_run,
    write_plan_changelog,
)
from ._history import (
    ALIAS_DEPENDENCY,
    ALIAS_PACKAGE,
    BRIDGE_PACKAGE,
    EXAMPLE_PYPROJECTS,
    PYPROJECT,
    RECIPE,
    RUNTIME_PYPROJECT,
    SCAFFOLD_WEB,
    TOOLS_PYPROJECT,
    UI_ALIAS_DEPENDENCY,
    UI_ALIAS_PACKAGE,
    UI_PACKAGE,
    UI_PEER,
    QgisSdkReleaseVersionError,
    list_tags,
)
from ._pins import (
    ManifestSources,
    ManifestVersions,
    has_scaffold_ui_pin,
    stamp_scaffold_pin,
    stamp_scaffold_ui_pin,
    ui_peer_range_includes,
)
from ._version import Version, normalize_scope


def cmd_plan(args: argparse.Namespace) -> int:
    config = parse_versionrc(Path(args.config).read_text(encoding="utf-8"))
    tags = list_tags()
    milestone_tag = getattr(args, "milestone_tag", "") or ""
    requested = requested_scope(args, tags, milestone_tag)
    commits = commits_since(
        tags, cli_plan_scope(requested, milestone_tag), args.suffix or ""
    )
    dry_run, dry_run_note = resolve_dry_run(
        args.trigger,
        str(getattr(args, "dry_run", "false")).strip().lower() in ("true", "1", "yes"),
    )
    plan = compute_plan(
        args.trigger,
        tags,
        commits,
        config,
        plan_options(args, requested, milestone_tag),
    )
    if dry_run_note:
        plan = replace(plan, reason=f"{plan.reason} ({dry_run_note})")
    emit_plan(plan, dry_run, write_plan_changelog(plan), args.json)
    return 0


@dataclass
class _StampRun:
    """The files one ``stamp`` of the Python train touches.

    Each manifest has its own step so the recipe text, which several of them
    amend in sequence, has one owner and one place to be written back.
    """

    scope: str
    version: Version
    stamped: list[str] = field(default_factory=list)
    recipe_text: str | None = None

    @property
    def split(self) -> bool:
        return RUNTIME_PYPROJECT.is_file() and TOOLS_PYPROJECT.is_file()

    @property
    def kit(self) -> bool:
        return self.scope in ("all", "python")

    @property
    def runtime(self) -> bool:
        return self.kit or self.scope == "runtime"

    @property
    def tools(self) -> bool:
        return self.kit or self.scope == "tools"

    def stamp_kit(self) -> None:
        if not self.kit:
            return
        text = PYPROJECT.read_text(encoding="utf-8")
        if self.split:
            text = stamp_kit_pins(text, self.version)
        PYPROJECT.write_text(stamp_pyproject(text, self.version), encoding="utf-8")
        self.stamped.append(f"{PYPROJECT} (PEP 440: {self.version.to_pep440()})")
        if self.recipe_text is not None:
            self.recipe_text = stamp_recipe(self.recipe_text, self.version)

    def stamp_runtime(self) -> None:
        if not (self.split and self.runtime):
            return
        text = RUNTIME_PYPROJECT.read_text(encoding="utf-8")
        RUNTIME_PYPROJECT.write_text(
            stamp_pyproject(text, self.version), encoding="utf-8"
        )
        self.stamped.append(str(RUNTIME_PYPROJECT))
        if self.recipe_text is not None and "runtime_version:" in self.recipe_text:
            self.recipe_text = stamp_recipe_context(
                self.recipe_text, "runtime_version", self.version
            )

    def stamp_tools(self) -> None:
        if not (self.split and self.tools):
            return
        # The range is what the tools were tested against: the runtime that is
        # at HEAD when they release (the one being stamped on the kit train).
        tested = (
            self.version
            if self.runtime
            else read_pyproject_version(RUNTIME_PYPROJECT.read_text(encoding="utf-8"))
        )
        text = TOOLS_PYPROJECT.read_text(encoding="utf-8")
        TOOLS_PYPROJECT.write_text(
            stamp_tools_runtime_range(stamp_pyproject(text, self.version), tested),
            encoding="utf-8",
        )
        self.stamped.append(
            f"{TOOLS_PYPROJECT} (runtime range >={tested},<{next_minor(tested)})"
        )
        if self.recipe_text is not None and "tools_version:" in self.recipe_text:
            self.recipe_text = stamp_recipe_context(
                self.recipe_text, "tools_version", self.version
            )
            if TOOLS_RUNTIME_RANGE.search(self.recipe_text):
                self.recipe_text = stamp_tools_runtime_range(self.recipe_text, tested)

    def stamp_recipe(self) -> None:
        changed = self.kit or (self.split and (self.runtime or self.tools))
        if self.recipe_text is None or not changed:
            return
        RECIPE.write_text(self.recipe_text, encoding="utf-8")
        self.stamped.append(str(RECIPE))

    def stamp_examples(self) -> None:
        moved = " and ".join(
            name
            for name, on in (("runtime", self.runtime), ("tools", self.tools))
            if on
        )
        for example in EXAMPLE_PYPROJECTS:
            if not example.is_file() or not (self.runtime or self.tools):
                continue
            example.write_text(
                stamp_example_windows(
                    example.read_text(encoding="utf-8"),
                    runtime=self.version if self.runtime else None,
                    tools=self.version if self.tools else None,
                ),
                encoding="utf-8",
            )
            self.stamped.append(
                f"{example} ({moved} window {minor_window(self.version)})"
            )

    def run(self) -> list[str]:
        self.stamp_kit()
        self.stamp_runtime()
        self.stamp_tools()
        self.stamp_recipe()
        self.stamp_examples()
        return self.stamped


def _stamp_python(scope: str, version: Version) -> list[str]:
    """Stamp the Python manifests a ``scope`` release owns; return what moved.

    ``python`` (and ``all``) is the kit train: kit, runtime and tools at one
    version, the kit re-pinned and the tools' tested range moved with the
    runtime. ``runtime`` moves the runtime manifest only; ``tools`` moves the
    tools manifest and its range, tested against the runtime at HEAD. The
    recipe carries one context version per distribution.
    """
    from ._verify import read_if_file

    return _StampRun(scope, version, recipe_text=read_if_file(RECIPE)).run()


def _stamp_typescript(version: Version) -> list[str]:
    """Stamp the bridge, its alias and the scaffold pin the TypeScript train owns."""
    stamped: list[str] = []
    package_text = BRIDGE_PACKAGE.read_text(encoding="utf-8")
    BRIDGE_PACKAGE.write_text(
        stamp_package_json(package_text, version), encoding="utf-8"
    )
    stamped.append(str(BRIDGE_PACKAGE))
    if ALIAS_PACKAGE.is_file():
        alias_text = ALIAS_PACKAGE.read_text(encoding="utf-8")
        ALIAS_PACKAGE.write_text(
            stamp_alias_package_json(alias_text, version), encoding="utf-8"
        )
        stamped.append(f"{ALIAS_PACKAGE} (and its pin on {ALIAS_DEPENDENCY})")
    if SCAFFOLD_WEB.is_file():
        web_text = SCAFFOLD_WEB.read_text(encoding="utf-8")
        SCAFFOLD_WEB.write_text(stamp_scaffold_pin(web_text, version), encoding="utf-8")
        stamped.append(f"{SCAFFOLD_WEB} (the pin qgis-sdk new offers)")
    return stamped


def _stamp_ui(version: Version) -> list[str]:
    """Stamp the web components, their alias and the UI scaffold pin."""
    stamped: list[str] = []
    ui_text = UI_PACKAGE.read_text(encoding="utf-8")
    UI_PACKAGE.write_text(stamp_package_json(ui_text, version), encoding="utf-8")
    stamped.append(str(UI_PACKAGE))
    if UI_ALIAS_PACKAGE.is_file():
        ui_alias_text = UI_ALIAS_PACKAGE.read_text(encoding="utf-8")
        UI_ALIAS_PACKAGE.write_text(
            stamp_alias_package_json(
                ui_alias_text, version, dependency=UI_ALIAS_DEPENDENCY
            ),
            encoding="utf-8",
        )
        stamped.append(f"{UI_ALIAS_PACKAGE} (and its pin on {UI_ALIAS_DEPENDENCY})")
    if SCAFFOLD_WEB.is_file():
        web_text = SCAFFOLD_WEB.read_text(encoding="utf-8")
        if has_scaffold_ui_pin(web_text):
            SCAFFOLD_WEB.write_text(
                stamp_scaffold_ui_pin(web_text, version), encoding="utf-8"
            )
            stamped.append(
                f"{SCAFFOLD_WEB} (the pin qgis-sdk new --ui-dependency offers)"
            )
    return stamped


def cmd_stamp(args: argparse.Namespace) -> int:
    version = Version.parse(args.version)
    scope = normalize_scope(getattr(args, "scope", "all") or "all")
    stamped: list[str] = []
    if scope in ("all", "python", "runtime", "tools"):
        stamped.extend(_stamp_python(scope, version))
    if scope in ("all", "typescript"):
        stamped.extend(_stamp_typescript(version))
    if scope == "ui":
        stamped.extend(_stamp_ui(version))
    print(f"stamped {version} for scope {scope} into {', '.join(stamped)}")
    return 0


def reported_example_windows(scope: str, versions: ManifestVersions) -> dict[str, str]:
    """The compatibility windows every example project declares for a release.

    The examples are what the released tools are qualified against; a window
    that excludes the release would make the stamped tools refuse them
    (VERSION004), so a mismatch is reported as a release error rather than a
    warning.
    """
    windows_reported: dict[str, str] = {}
    for example in EXAMPLE_PYPROJECTS:
        if not example.is_file():
            continue
        windows = read_example_windows(example.read_text(encoding="utf-8"))
        released = {
            "qgis-sdk-runtime": versions.runtime if scope != "tools" else None,
            "qgis-sdk-tools": versions.tools if scope != "runtime" else None,
        }
        for name, (lower, upper) in windows.items():
            windows_reported[f"{example_label(example)}: {name}"] = (
                f">={lower},<{upper}"
            )
            shipped = released[name]
            if shipped is None or example_window_includes(lower, upper, shipped):
                continue
            raise QgisSdkReleaseVersionError(
                f"{example_label(example)} declares {name}>={lower},<{upper} "
                f"but this release ships {name} {shipped}; run stamp --scope "
                f"{scope} --version {shipped} so the example follows"
            )
    return windows_reported


def manifest_sources() -> ManifestSources:
    """Read every manifest a verification needs, tolerating optional files."""
    from ._verify import read_if_file

    return ManifestSources(
        pyproject_text=PYPROJECT.read_text(encoding="utf-8"),
        package_text=BRIDGE_PACKAGE.read_text(encoding="utf-8"),
        recipe_text=read_if_file(RECIPE),
        alias_text=read_if_file(ALIAS_PACKAGE),
        runtime_text=read_if_file(RUNTIME_PYPROJECT),
        tools_text=read_if_file(TOOLS_PYPROJECT),
        scaffold_text=read_if_file(SCAFFOLD_WEB),
        ui_text=read_if_file(UI_PACKAGE),
        ui_alias_text=read_if_file(UI_ALIAS_PACKAGE),
    )


def wanted_scopes(sources: ManifestSources, scope_raw: str) -> tuple[str, ...]:
    """The scopes one verification has to answer for."""
    if scope_raw:
        return (normalize_scope(scope_raw),)
    ui_scopes: tuple[str, ...] = ("ui",) if sources.ui_text is not None else ()
    split = sources.runtime_text is not None and sources.tools_text is not None
    if split:
        # Without a release in hand each distribution only has to agree with
        # itself: the runtime or the tools may have released alone since the
        # last kit, so the kit's pins may lag them, never lead them.
        return ("runtime", "tools", "kit", "typescript", *ui_scopes)
    return ("python", "typescript", *ui_scopes)


def check_ui_peer(scope: str, versions: ManifestVersions, entry: dict) -> None:
    """A UI release must accept the bridge it was tested against."""
    if scope != "ui" or versions.ui_peer_range is None:
        return
    lower, upper = versions.ui_peer_range
    if not ui_peer_range_includes(versions.ui_peer_range, versions.package_json):
        raise QgisSdkReleaseVersionError(
            f"the ui package declares {UI_PEER} >={lower} <{upper} as its "
            f"peer but the bridge at HEAD is {versions.package_json}; widen "
            "the peer range in packages/qgis-sdk-ui/package.json before a "
            "ui release"
        )
    entry["bridge_peer_range"] = f">={lower} <{upper}"


def check_runtime_range(
    scope: str, versions: ManifestVersions, tools_text: str | None, entry: dict
) -> None:
    """The tools' tested range must hold the runtime they ship next to."""
    if scope not in ("python", "runtime", "tools"):
        return
    if not tools_text or versions.runtime is None:
        return
    lower, upper = read_tools_runtime_range(tools_text)
    if not runtime_range_includes(lower, upper, versions.runtime):
        raise QgisSdkReleaseVersionError(
            f"the tools were tested against qgis-sdk-runtime>={lower},<{upper} "
            f"but the runtime at HEAD is {versions.runtime}; a tools release "
            "must include the runtime it ships next to (stamp --scope tools, "
            "or release the kit with --scope python)"
        )
    entry["runtime_range"] = f">={lower},<{upper}"


def check_expected_version(scope, scoped, version, expected) -> None:
    """A named release must already be the version every manifest carries."""
    if expected is None or version == expected:
        return
    listed = ", ".join(f"{name}={value}" for name, value in scoped)
    raise QgisSdkReleaseVersionError(
        f"scope {scope} is releasing {expected}, but its manifests carry "
        f"{listed}; run stamp --scope {scope} --version {expected} first"
    )
