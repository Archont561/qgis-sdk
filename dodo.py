"""The task registry: ``pixi run automation <task>``.

`doit <https://pydoit.org>`_ discovers the ``task_*`` functions below, so this
file is the only place a task is described and the only file that imports the
runner. The work itself lives in :mod:`automation.tasks`, which is ordinary
Python and stays importable and testable without doit in the picture.

Nothing here declares ``file_dep`` or ``targets`` on purpose. Every task is a
gate or a publish step whose answer depends on the whole checkout; caching one
would turn "the tree is fine" into "nothing changed since the last time it was
fine", and a release step that silently skips is worse than one that reruns.

    pixi run automation list
    pixi run automation lint_python
    pixi run automation release_plan --trigger dispatch --dry-run false
    pixi run automation -n 4 lint_python lint_repository docs_lint
"""

from __future__ import annotations

import functools

from automation import tasks


def action(function):
    """Adapt an automation function to doit's return contract.

    The functions in :mod:`automation.tasks` return the exit status their
    command would have had, so a test can assert on it. doit's Python actions
    instead return ``None`` for success and ``False`` for failure, and reject an
    ``int`` - this is the one place the two conventions meet.
    """

    @functools.wraps(function)
    def run(**kwargs):
        return None if not function(**kwargs) else False

    return run


DOIT_CONFIG = {
    # `verbosity: 2` prints the command each task runs, which is the whole point
    # of a CLI that replaces hand-typed commands.
    "verbosity": 2,
    # `pixi run automation` with nothing after it lists the vocabulary.
    "default_tasks": ["list"],
}


# --- gates ----------------------------------------------------------------


def task_lint_python():
    """Lint every Python tree with Ruff."""
    return {"actions": [action(tasks.lint_python)]}


def task_format_check():
    """Fail when a Python file is not formatted the way Ruff formats it."""
    return {"actions": [action(tasks.format_check)]}


def task_clean_code():
    """Gate the Clean Code metrics against the committed budget."""
    return {
        "actions": [action(tasks.clean_code)],
        "params": [
            {
                "name": "rebaseline",
                "long": "rebaseline",
                "default": False,
                "type": bool,
                "help": "rewrite the budget from the live run",
            }
        ],
    }


def task_lint_repository():
    """Apply the repository policy rules (Alint) to the whole checkout."""
    return {"actions": [action(tasks.lint_repository)]}


def task_lint_actions():
    """Lint the GitHub Actions workflows."""
    return {"actions": [action(tasks.lint_actions)]}


def task_lint_features():
    """Lint every Gherkin scenario with gherlint."""
    return {"actions": [action(tasks.lint_features)]}


def task_check_commits():
    """Check the commits in range against the conventional-commit rules."""
    return {"actions": [action(tasks.check_commits)]}


def task_check():
    """Run the fast local gates: Ruff, clean code, Alint and actionlint."""
    return {
        "actions": [],
        "task_dep": [
            "lint_python",
            "format_check",
            "clean_code",
            "lint_repository",
            "lint_actions",
        ],
    }


# --- tests ----------------------------------------------------------------


def task_test_python():
    """Run the QGIS-free suite of the Python kit."""
    return {"actions": [action(tasks.test_python)]}


def task_test_scripts():
    """Run the repository script tests and the README mirror rules."""
    return {"actions": [action(tasks.test_scripts)]}


def task_test_alint_policy():
    """Run the tests of the Alint policy itself."""
    return {"actions": [action(tasks.test_alint_policy)]}


def task_native():
    """Run the native suite that needs a QGIS host."""
    return {"actions": [action(tasks.native)]}


def task_reference_example():
    """Run the reference plugins through their own `qgis-sdk test`."""
    return {"actions": [action(tasks.test_reference_example)]}


def task_check_generated():
    """Fail when a generated bridge client is stale."""
    return {"actions": [action(tasks.check_generated)]}


# --- JavaScript workspace -------------------------------------------------


def task_install_js():
    """Install the JavaScript workspace from the lockfile."""
    return {"actions": [action(tasks.install_js)]}


def task_biome():
    """Lint and format-check the JavaScript and TypeScript trees."""
    return {"actions": [action(tasks.biome)]}


def task_typecheck():
    """Typecheck the bridge and the web components."""
    return {"actions": [action(tasks.typecheck)]}


def task_test_js():
    """Run every JavaScript package's tests through turborepo."""
    return {"actions": [action(tasks.turbo_test)]}


def task_test_reference_web():
    """Run the reference page's tests on the workspace bridge."""
    return {"actions": [action(tasks.test_reference_web)]}


def task_storybook():
    """Build the Storybook of the web components."""
    return {"actions": [action(tasks.storybook)]}


def task_agents_check():
    """Fail when the generated regions of AGENTS.md are stale."""
    return {"actions": [action(tasks.agents_check)]}


def task_coverage():
    """Run the JavaScript coverage suite, keeping the log CI annotates."""
    return {"actions": [action(tasks.coverage)]}


def task_docs_build():
    """Build the documentation site as a static export."""
    return {"actions": [action(tasks.docs_build)]}


def task_docs_lint():
    """Lint the Markdown of the documentation site."""
    return {"actions": [action(tasks.docs_lint)]}


def task_docs_link_check():
    """Check every internal link of the built site."""
    return {"actions": [action(tasks.docs_link_check)]}


# --- the harness, for a task graph ---------------------------------------


def task_run_log():
    """Run a command and keep its output in a log for a later annotation."""
    return {
        "actions": [action(tasks.run_log)],
        "params": [
            {
                "name": "log",
                "long": "log",
                "default": "step.log",
                "type": str,
                "help": "file the command's output is written to",
            },
            {
                "name": "command",
                "long": "command",
                "default": None,
                "type": list,
                "help": "the command to run, repeated or space-separated",
            },
        ],
    }


def task_annotate_log():
    """Turn the tail of a captured log into a workflow annotation."""
    return {
        "actions": [action(tasks.annotate_log)],
        "params": [
            {
                "name": "log",
                "long": "log",
                "default": "",
                "type": str,
                "help": "log to read",
            },
            {
                "name": "title",
                "long": "title",
                "default": "failed step",
                "type": str,
                "help": "annotation title",
            },
            {
                "name": "tail",
                "long": "tail",
                "default": 25,
                "type": int,
                "help": "how many lines to show",
            },
            {
                "name": "skip_missing",
                "long": "skip-missing",
                "default": False,
                "type": bool,
                "help": "do nothing when the log was never written",
            },
        ],
    }


def task_annotate_coverage():
    """Annotate the coverage failures of a captured coverage log."""
    return {
        "actions": [action(tasks.annotate_coverage)],
        "params": [
            {
                "name": "log",
                "long": "log",
                "default": "coverage-output.log",
                "type": str,
                "help": "coverage log to read",
            }
        ],
    }


def task_report_bun():
    """Annotate the failing JavaScript tests of a captured log."""
    return {
        "actions": [action(tasks.report_bun)],
        "params": [
            {
                "name": "log",
                "long": "log",
                "default": "",
                "type": str,
                "help": "log to read",
            },
            {
                "name": "title",
                "long": "title",
                "default": "bun test",
                "type": str,
                "help": "annotation title",
            },
        ],
    }


def task_report_steps():
    """Summarise every failed workflow step that recorded itself."""
    return {"actions": [action(tasks.report_steps)]}


def task_bun_ui():
    """Run the headless UI probe of the reference page."""
    return {"actions": [action(tasks.bun_ui)]}


def task_commit_base():
    """Publish the merge base the commit-message gate checks against."""
    return {"actions": [action(tasks.commit_base)]}


def task_test_results():
    """Turn a JUnit XML report into the failure annotation a job shows."""
    return {
        "actions": [action(tasks.test_results)],
        "params": [
            {
                "name": "report",
                "long": "report",
                "default": "",
                "type": str,
                "help": "JUnit XML file",
            },
            {
                "name": "title",
                "long": "title",
                "default": "",
                "type": str,
                "help": "annotation title",
            },
        ],
    }


# --- release train --------------------------------------------------------

_PLAN_PARAMS = [
    {
        "name": "trigger",
        "long": "trigger",
        "default": "push",
        "type": str,
        "choices": (
            ("push", "push"),
            ("dispatch", "dispatch"),
            ("milestone", "milestone"),
        ),
        "help": "what asked for the release",
    },
    {
        "name": "scope",
        "long": "scope",
        "default": "",
        "type": str,
        "help": "auto, all, python or typescript",
    },
    {
        "name": "bump",
        "long": "bump",
        "default": "",
        "type": str,
        "help": "force a major/minor/patch bump",
    },
    {
        "name": "suffix",
        "long": "suffix",
        "default": "",
        "type": str,
        "help": "prerelease suffix, e.g. rc.1",
    },
    {
        "name": "version_override",
        "long": "version-override",
        "default": "",
        "type": str,
        "help": "an exact version",
    },
    {
        "name": "milestone_tag",
        "long": "milestone-tag",
        "default": "",
        "type": str,
        "help": "the milestone tag triggering this",
    },
    {
        "name": "dry_run",
        "long": "dry-run",
        "default": "false",
        "type": str,
        "choices": (("true", "true"), ("false", "false")),
        "help": "report without acting",
    },
    {
        "name": "json",
        "long": "json",
        "default": False,
        "type": bool,
        "help": "machine-readable output",
    },
]


def task_release_plan():
    """Decide what the next release is: nothing, a rehearsal, or a tag."""
    return {"actions": [action(tasks.release_plan)], "params": _PLAN_PARAMS}


def task_release_classify():
    """Classify one release tag into its scope."""
    return {
        "actions": [action(tasks.release_classify)],
        "params": [
            {
                "name": "tag",
                "long": "tag",
                "default": "",
                "type": str,
                "help": "the tag to classify",
            },
            {
                "name": "scoped",
                "long": "scoped",
                "default": False,
                "type": bool,
                "help": "expect a scoped tag",
            },
        ],
    }


def task_release_tag():
    """Create the annotated release tag, optionally pushing it."""
    return {
        "actions": [action(tasks.release_tag)],
        "params": [
            {
                "name": "tag",
                "long": "tag",
                "default": "",
                "type": str,
                "help": "tag name",
            },
            {
                "name": "message_file",
                "long": "message-file",
                "default": "",
                "type": str,
                "help": "file holding the annotation",
            },
            {
                "name": "message",
                "long": "message",
                "default": "",
                "type": str,
                "help": "annotation text",
            },
            {
                "name": "push",
                "long": "push",
                "default": False,
                "type": bool,
                "help": "push the tag",
            },
        ],
    }


def task_release_stamp():
    """Stamp one version into the manifests of a scope."""
    return {
        "actions": [action(tasks.release_stamp)],
        "params": [
            {
                "name": "version",
                "long": "version",
                "default": "",
                "type": str,
                "help": "version to stamp",
            },
            {
                "name": "scope",
                "long": "scope",
                "default": "all",
                "type": str,
                "help": "all, python or typescript",
            },
        ],
    }


def task_release_verify_versions():
    """Require one version per released scope and one shared contract version."""
    return {
        "actions": [action(tasks.release_verify_versions)],
        "params": [
            {
                "name": "scope",
                "long": "scope",
                "default": "",
                "type": str,
                "help": "all, python or typescript",
            },
            {
                "name": "version",
                "long": "version",
                "default": "",
                "type": str,
                "help": "version this scope releases",
            },
            {
                "name": "json",
                "long": "json",
                "default": False,
                "type": bool,
                "help": "machine-readable output",
            },
        ],
    }


def task_release_build_python():
    """Build and check the wheel of every Python distribution in scope."""
    return {
        "actions": [action(tasks.release_build_python)],
        "params": [
            {
                "name": "scope",
                "long": "scope",
                "default": "all",
                "type": str,
                "help": "all, python, runtime or tools",
            },
            {
                "name": "outdir",
                "long": "outdir",
                "default": "dist/pypi",
                "type": str,
                "help": "where the wheels land",
            },
            {
                "name": "package",
                "long": "package",
                "default": None,
                "type": list,
                "help": "package directories to build",
            },
        ],
    }


def task_release_verify_python():
    """Twine-check the wheels that were built."""
    return {
        "actions": [action(tasks.release_verify_python)],
        "params": [
            {
                "name": "dist",
                "long": "dist",
                "default": "dist/pypi",
                "type": str,
                "help": "directory holding the wheels",
            }
        ],
    }


def task_release_checksums():
    """Write a `SHA256SUMS` file over the release assets."""
    return {
        "actions": [action(tasks.release_checksums)],
        "params": [
            {
                "name": "out",
                "long": "out",
                "default": "SHA256SUMS",
                "type": str,
                "help": "file to write",
            },
            {
                "name": "paths",
                "long": "paths",
                "default": None,
                "type": list,
                "help": "assets to hash",
            },
        ],
    }


def task_release_github_release():
    """Publish the GitHub Release for a tag."""
    return {
        "actions": [action(tasks.release_github_release)],
        "params": [
            {
                "name": "tag",
                "long": "tag",
                "default": "",
                "type": str,
                "help": "tag the release is for",
            },
            {
                "name": "body_file",
                "long": "body-file",
                "default": "",
                "type": str,
                "help": "file holding the notes",
            },
            {
                "name": "asset",
                "long": "asset",
                "default": None,
                "type": list,
                "help": "assets to upload",
            },
            {
                "name": "repo",
                "long": "repo",
                "default": "",
                "type": str,
                "help": "owner/name, defaults to this checkout",
            },
        ],
    }
