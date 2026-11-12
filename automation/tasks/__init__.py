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

from ._bun import (
    agents_check,
    biome,
    bun_ui,
    coverage,
    docs_build,
    docs_link_check,
    docs_lint,
    install_js,
    storybook,
    test_reference_web,
    turbo_test,
    typecheck,
)
from ._gates import (
    check_commits,
    check_generated,
    clean_code,
    format_check,
    lint_actions,
    lint_features,
    lint_python,
    lint_repository,
    native,
    pr_watch,
    test_alint_policy,
    test_python,
    test_reference_example,
    test_scripts,
)
from ._harness import (
    annotate_coverage,
    annotate_log,
    commit_base,
    report_bun,
    report_steps,
    run_log,
    test_results,
)
from ._release import (
    release_build_python,
    release_checksums,
    release_classify,
    release_github_release,
    release_plan,
    release_stamp,
    release_tag,
    release_verify_python,
    release_verify_versions,
)

__all__ = [
    "agents_check",
    "annotate_coverage",
    "annotate_log",
    "biome",
    "bun_ui",
    "check_commits",
    "check_generated",
    "clean_code",
    "commit_base",
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
    "pr_watch",
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
    "test_results",
    "test_scripts",
    "turbo_test",
    "typecheck",
]
