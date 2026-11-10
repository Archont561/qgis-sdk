"""The automation commands, as plain Python functions.

``dodo.py`` is the registry and the only thing that knows about ``doit``. Every
function here can be called from a test, from another task, or from ``python -c``
without a task runner in the picture, and each returns the exit status the
command would have had.

Two kinds of task live here:

- **Gates** the checkout runs on itself - lint, format, tests, docs, the Bun
  workspace - which used to be one-line Pixi tasks. They now share one
  vocabulary and can be sequenced with ``task_dep``.
- **Release train steps** which forward to :mod:`automation.release`. The tool
  stays stdlib-only and independently runnable, because ``autorelease.yml``
  plans and tags before a Pixi environment exists.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

from automation import ci, commits, release, results
from automation.lib import pixi, run

__all__ = [
    "agents_check",
    "annotate_coverage",
    "annotate_log",
    "biome",
    "bun_ui",
    "check_commits",
    "check_generated",
    "coverage",
    "docs_build",
    "docs_link_check",
    "docs_lint",
    "format_check",
    "install_js",
    "lint_actions",
    "lint_features",
    "lint_python",
    "lint_repository",
    "native",
    "release_build_python",
    "release_checksums",
    "release_classify",
    "release_github_release",
    "release_plan",
    "release_stamp",
    "release_tag",
    "release_verify_python",
    "release_verify_versions",
    "report_bun",
    "report_steps",
    "run_log",
    "storybook",
    "test_alint_policy",
    "test_python",
    "test_reference_example",
    "test_reference_web",
    "test_scripts",
    "turbo_test",
    "typecheck",
]

PYTEST = [sys.executable, "-m", "pytest"]


# --- gates ----------------------------------------------------------------


def lint_python() -> int:
    """Lint every Python tree with Ruff (scope lives in ``ruff.toml``)."""
    return run(["ruff", "check", "."])


def format_check() -> int:
    """Fail when a Python file is not formatted the way Ruff formats it."""
    return run(["ruff", "format", "--check", "."])


def lint_actions() -> int:
    """Lint the GitHub Actions workflows with actionlint."""
    workflows = sorted(str(path) for path in Path(".github/workflows").glob("*.yml"))
    return run(["actionlint", *workflows])


def lint_repository() -> int:
    """Apply the repository policy rules (Alint) to the whole checkout."""
    return run(["alint", "check", "."])


def check_commits() -> int:
    """Check the commits in the range against the conventional-commit rules."""
    return run(["convco", "check"])


def test_scripts() -> int:
    """Run the repository script tests and the README mirror rules."""
    status = run([*PYTEST, "-c", "tests/scripts/pyproject.toml", "tests/scripts", "-q"])
    if status:
        return status
    return run(
        [
            "alint",
            "check",
            "--only",
            "bridge-readme-mirror",
            "--only",
            "ui-readme-mirror",
            "--only",
            "bridge-readme-alias-name",
            "--only",
            "ui-readme-alias-name",
            ".",
        ]
    )


def test_alint_policy() -> int:
    """Run the tests of the Alint policy itself."""
    return run([*PYTEST, "-c", "tests/scripts/pyproject.toml", "tests/alint", "-q"])


def test_python() -> int:
    """Run the QGIS-free suite of the Python kit."""
    return run(
        [
            *PYTEST,
            "-c",
            "packages/qgis-sdk-python/pyproject.toml",
            "packages/qgis-sdk-python/tests",
            "-q",
        ]
    )


def native() -> int:
    """Run the native suite and annotate the tests a failure names."""
    return ci.native(list(ci.NATIVE_COMMAND))


def check_generated() -> int:
    """Fail when a generated bridge client is stale."""
    return ci.check_generated()


def test_reference_example() -> int:
    """Run the reference plugins through their own ``qgis-sdk test``."""
    # The reference page is exercised without a display; the Pixi task used to
    # carry this, and the task is where it belongs now that CI calls the task.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return ci.reference_example()


def lint_features() -> int:
    """Lint every Gherkin scenario with gherlint.

    gherlint pins pydantic 1, which cannot share an environment with the
    runtime's pydantic 2, so it gets a throwaway venv beside the Pixi
    environments - gitignored, reused between runs.
    """
    venv = Path(".pixi/gherkin")
    python = venv / "bin/python"
    if not python.exists():
        status = run([sys.executable, "-m", "venv", str(venv)])
        if status:
            return status
        status = run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--quiet",
                "--disable-pip-version-check",
                "gherlint==0.5.0",
            ]
        )
        if status:
            return status
    return ci.check_gherkin(str(venv / "bin/gherlint"))


def coverage() -> int:
    """Run the JavaScript coverage suite, writing the log CI annotates."""
    return ci.run_logged(
        ["pixi", "run", "-e", "bun", "bun", "run", "coverage"],
        Path("coverage-output.log"),
    )


# --- Bun workspace --------------------------------------------------------


def install_js() -> int:
    """Install the JavaScript workspace from the lockfile."""
    return pixi("bun", "install-js")


def biome() -> int:
    """Lint and format-check the JavaScript and TypeScript trees."""
    return pixi("bun", "biome-check")


def typecheck() -> int:
    """Typecheck the bridge and the web components."""
    return pixi("bun", "typecheck")


def turbo_test() -> int:
    """Run every JavaScript package's tests through turborepo."""
    return pixi("bun", "turbo-test")


def test_reference_web() -> int:
    """Run the reference page's tests on the workspace bridge."""
    return pixi("bun", "test-reference-web")


def storybook() -> int:
    """Build the Storybook of the web components."""
    return pixi("bun", "storybook-build")


def docs_build() -> int:
    """Build the documentation site as a static export."""
    return pixi("bun", "docs-build")


def docs_link_check() -> int:
    """Check every internal link of the built site."""
    status = docs_build()
    if status:
        return status
    return pixi("bun", "docs-link-check")


def docs_lint() -> int:
    """Lint the Markdown of the documentation site."""
    return pixi("bun", "lint-docs")


def agents_check() -> int:
    """Fail when the generated regions of ``AGENTS.md`` are stale."""
    return pixi("bun", "bun", "run", "agents:check")


# --- the harness, available to a task graph -------------------------------


def run_log(log: str, command: Sequence[str] | None = None) -> int:
    """Run ``command``, keeping its output in ``log`` for a later annotation."""
    return ci.run_logged(list(command or []), Path(log))


def annotate_log(
    log: str, title: str = "failed step", tail: int = 25, skip_missing: bool = False
) -> int:
    """Turn the tail of a captured log into a workflow annotation."""
    ci.annotate_log(Path(log), title=title, tail=tail, skip_missing=skip_missing)
    return 0


def annotate_coverage(log: str) -> int:
    """Annotate the coverage failures of a captured coverage log."""
    ci.annotate_coverage(Path(log))
    return 0


def report_bun(log: str, title: str) -> int:
    """Annotate the failing JavaScript tests of a captured log."""
    ci.report_bun(Path(log), title)
    return 0


def report_steps() -> int:
    """Summarise every failed workflow step that recorded itself."""
    ci.report_steps()
    return 0


def bun_ui() -> int:
    """Run the headless UI probe of the reference page."""
    return ci.bun_ui()


def commit_base() -> int:
    """Publish ``BASE_SHA``/``BASE_REF`` for the commit-message gate."""
    return commits.main()


def test_results(report: str, title: str = "") -> int:
    """Turn a JUnit XML report into the failure annotation a job shows."""
    return results.main([report, *(["--title", title] if title else [])])


# --- release train --------------------------------------------------------


def _release_command(command: str, **options: object) -> int:
    """Forward a set of named options to one ``release`` subcommand."""
    argv = [command]
    for name, value in options.items():
        if value is None or value == "" or value is False or value == []:
            continue
        flag = "--" + name.replace("_", "-")
        if value is True:
            argv.append(flag)
        elif isinstance(value, (list, tuple)):
            argv.append(flag)
            argv.extend(str(item) for item in value)
        else:
            argv.extend([flag, str(value)])
    return release.main(argv)


def release_plan(
    trigger: str = "push",
    config: str = "",
    suffix: str = "",
    version_override: str = "",
    scope: str = "",
    bump: str = "",
    milestone_tag: str = "",
    dry_run: str = "false",
    json: bool = False,
) -> int:
    """Decide what the next release is: nothing, a rehearsal, or a tag."""
    return _release_command(
        "plan",
        trigger=trigger,
        config=config,
        suffix=suffix,
        version_override=version_override,
        scope=scope,
        bump=bump,
        milestone_tag=milestone_tag,
        dry_run=dry_run,
        json=json,
    )


def release_classify(tag: str, scoped: bool = False) -> int:
    """Classify one release tag into its scope."""
    return _release_command("classify", tag=tag, scoped=scoped)


def release_tag(
    tag: str = "", message: str = "", message_file: str = "", push: bool = False
) -> int:
    """Create the annotated release tag, optionally pushing it."""
    return _release_command(
        "tag", tag=tag, message=message, message_file=message_file, push=push
    )


def release_stamp(version: str, scope: str = "all") -> int:
    """Stamp one version into the manifests of a scope."""
    return _release_command("stamp", version=version, scope=scope)


def release_verify_versions(
    scope: str = "", version: str = "", json: bool = False
) -> int:
    """Require one version per released scope and one shared contract version."""
    return _release_command("verify-versions", scope=scope, version=version, json=json)


def release_build_python(
    package: Sequence[str] | None = None, scope: str = "all", outdir: str = "dist/pypi"
) -> int:
    """Build and check the wheel of every Python distribution in scope."""
    return _release_command(
        "build-python", package=list(package or []), scope=scope, outdir=outdir
    )


def release_verify_python(dist: str = "dist/pypi") -> int:
    """Twine-check the wheels that were built."""
    return _release_command("verify-python", dist=dist)


def release_checksums(paths: Sequence[str], out: str = "SHA256SUMS") -> int:
    """Write a ``SHA256SUMS`` file over the release assets."""
    return _release_command("checksums", out=out, paths=list(paths))


def release_github_release(
    tag: str,
    body_file: str = "",
    asset: Sequence[str] | None = None,
    repo: str = "",
    token: str = "",
) -> int:
    """Publish the GitHub Release for a tag."""
    return _release_command(
        "github-release",
        tag=tag,
        body_file=body_file,
        asset=list(asset or []),
        repo=repo,
        token=token,
    )
