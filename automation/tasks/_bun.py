"""The Bun workspace gates, forwarded to the Pixi tasks that own them."""

from __future__ import annotations

from pathlib import Path

from automation import ci
from automation.lib import pixi

__all__ = [
    "agents_check",
    "biome",
    "bun_ui",
    "coverage",
    "docs_build",
    "docs_link_check",
    "docs_lint",
    "install_js",
    "storybook",
    "test_reference_web",
    "turbo_test",
    "typecheck",
]


def coverage() -> int:
    """Run the JavaScript coverage suite, writing the log CI annotates."""
    return ci.run_logged(
        ["pixi", "run", "-e", "bun", "bun", "run", "coverage"],
        Path("coverage-output.log"),
    )


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


def bun_ui() -> int:
    """Run the headless UI probe of the reference page."""
    return ci.bun_ui()
