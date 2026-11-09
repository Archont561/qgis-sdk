"""Exercise CI helper commands without a runner, QGIS, or live GitHub Actions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "automation" / "ci.py"


def run_ci(*args: str, cwd: Path, env: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_log_tees_both_streams_and_returns_the_command_status(tmp_path: Path):
    result = run_ci(
        "run-log",
        "output.log",
        "--",
        sys.executable,
        "-c",
        "import sys; print('stdout', flush=True); print('stderr', file=sys.stderr); sys.exit(7)",
        cwd=tmp_path,
    )
    assert result.returncode == 7
    assert "stdout" in result.stdout and "stderr" in result.stdout
    assert (tmp_path / "output.log").read_text() == result.stdout


def test_native_skipped_runtime_is_warning_only_for_pytest_exit_five(tmp_path: Path):
    command = "import sys; print('SKIPPED: native forms need PyQt'); sys.exit(5)"
    result = run_ci("native", "--", sys.executable, "-c", command, cwd=tmp_path)
    assert result.returncode == 0
    assert (
        "::warning::native layers did not run: native forms need PyQt" in result.stdout
    )
    assert "native forms need PyQt" in (tmp_path / "native-layers.log").read_text()


def test_native_failure_retains_status_and_annotates_log(tmp_path: Path):
    command = "import sys; print('FAIL 20%\\rcontinued'); sys.exit(3)"
    result = run_ci("native", "--", sys.executable, "-c", command, cwd=tmp_path)
    assert result.returncode == 3
    assert "::error title=native layers: environment::" in result.stdout
    assert "::error title=native layers: pytest::" in result.stdout
    assert "FAIL 20%25continued" in result.stdout


def test_native_failure_names_every_failed_test_before_the_log_tail(tmp_path: Path):
    """The tail is the last few tracebacks; the summary names all of them."""
    command = (
        "import sys; print('running'); "
        "print('FAILED tests/test_a.py::test_one - AssertionError: 1 != 2'); "
        "print('FAILED tests/test_b.py::test_two - ValueError'); "
        "print('24 failed, 321 passed'); sys.exit(1)"
    )
    result = run_ci("native", "--", sys.executable, "-c", command, cwd=tmp_path)
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    named = next(
        line
        for line in lines
        if line.startswith("::error title=native layers: 2 failed")
    )
    assert "tests/test_a.py::test_one" in named and "tests/test_b.py::test_two" in named
    # Both are inside one annotation, in the order pytest reported them.
    assert named.index("test_one") < named.index("test_two")
    # The annotation carries the summary lines and their reasons, not the run.
    assert "running" not in named
    assert named.count("%0A") == 1


def test_reference_example_names_the_failed_test_it_ran(tmp_path: Path):
    """The step was three commands joined by ``&&``: the second never ran after
    the first failed and the job said only "exit code 1".

    Each run now keeps a log of its own, so the annotation names the test that
    failed instead of the rerun that has to rediscover it.
    """
    command = (
        "import sys; print('running'); "
        "print('FAILED examples/simple/tests/test_workflow_qgis.py::test_raster - "
        "AssertionError: (0.1, 0.1) != (0.1000000'); "
        "print('1 failed, 24 passed'); sys.exit(1)"
    )
    result = run_ci(
        "reference-example", "--", sys.executable, "-c", command, cwd=tmp_path
    )
    assert result.returncode == 1
    named = next(
        line
        for line in result.stdout.splitlines()
        if line.startswith("::error title=reference example: override: 1 failed")
    )
    assert "test_workflow_qgis.py::test_raster" in named
    assert "0.1000000" in named
    assert "running" not in named
    logged = (tmp_path / "reference-example" / "override.log").read_text()
    assert "1 failed, 24 passed" in logged


def test_reference_example_leaves_a_green_run_without_annotations(tmp_path: Path):
    result = run_ci(
        "reference-example",
        "--",
        sys.executable,
        "-c",
        "print('25 passed')",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "::error" not in result.stdout
    assert "25 passed" in (tmp_path / "reference-example" / "override.log").read_text()


def test_annotations_limit_coverage_and_report_failed_steps(tmp_path: Path):
    log = tmp_path / "coverage-output.log"
    log.write_text("\n".join(f"ERROR case {n}" for n in range(45)), encoding="utf-8")
    report = run_ci("annotate-coverage", str(log), cwd=tmp_path)
    assert report.returncode == 0
    lines = report.stdout.splitlines()
    assert len(lines) == 40 and lines[0].endswith("6:ERROR case 5")
    steps = json.dumps(
        {"ok": {"conclusion": "success"}, "s11": {"conclusion": "failure"}}
    )
    report = run_ci("report-steps", cwd=tmp_path, env={"STEPS": steps})
    assert report.stdout == "::error title=failed step::s11\n"


def test_a_crashed_coverage_run_annotates_the_stack_under_the_marker(
    tmp_path: Path,
):
    """A segfault leaves no FAILED line; the stack under it is the report."""
    log = tmp_path / "coverage-output.log"
    log.write_text(
        "packages/qgis-sdk-python/tests/test_lts_native.py .....Fatal Python error: "
        "Segmentation fault\n"
        "\n"
        "Current thread 0x00007f (most recent call first):\n"
        '  File "/repo/src/qgis_sdk/adapters/qgis/jobs.py", line 61 in _tick\n'
        "Segmentation fault (core dumped)\n",
        encoding="utf-8",
    )

    report = run_ci("annotate-coverage", str(log), cwd=tmp_path)

    lines = report.stdout.splitlines()
    # The crash is the report: the matched aftermath would only crowd out the
    # frames, which a step's annotation cap would drop.
    assert lines[0].startswith(
        "::error title=interpreter died::1:packages/qgis-sdk-python/tests/test_lts"
    )
    assert lines[2].startswith("::error title=interpreter died::3:Current thread")
    assert lines[3].endswith("line 61 in _tick")
    assert lines[-1].startswith(
        "::error title=interpreter died::5:Segmentation fault (core dumped)"
    )


def test_a_failed_step_repeats_its_log_tail_and_skips_a_log_it_never_wrote(
    tmp_path: Path,
):
    """A failed build step annotates its tail; a step never reached stays quiet."""
    log = tmp_path / "docs-links.log"
    log.write_text("\n".join(f"line {n}" for n in range(40)), encoding="utf-8")

    report = run_ci(
        "annotate-log", str(log), "--title", "docs links", "--tail", "3", cwd=tmp_path
    )

    assert report.stdout.splitlines() == [
        "::error title=docs links::line 37",
        "::error title=docs links::line 38",
        "::error title=docs links::line 39",
    ]

    missing = str(tmp_path / "docs-build.log")
    quiet = run_ci(
        "annotate-log", missing, "--title", "docs build", "--skip-missing", cwd=tmp_path
    )
    assert quiet.returncode == 0
    assert quiet.stdout == ""

    loud = run_ci("annotate-log", missing, "--title", "docs build", cwd=tmp_path)
    assert "no log at" in loud.stdout


def test_bun_summary_first_match_or_missing_log(tmp_path: Path):
    log = tmp_path / "bun.log"
    log.write_text("12 pass\n42 pass\n", encoding="utf-8")
    report = run_ci("report-bun", str(log), "--title", "bun test", cwd=tmp_path)
    assert report.stdout == "::notice::bun test: 12 pass\n"
    report = run_ci(
        "report-bun", "absent.log", "--title", "bun test (qgis-sdk-ui)", cwd=tmp_path
    )
    assert report.returncode == 0
    assert report.stdout == "::notice::bun test (qgis-sdk-ui): no summary line\n"


def test_generated_gate_runs_generator_git_sweep_and_reference_check(tmp_path: Path):
    # Copy the entrypoint into a throwaway tree so its own repo root is isolated.
    script = tmp_path / "automation/ci.py"
    script.parent.mkdir()
    script.write_bytes(SCRIPT.read_bytes())
    generator = tmp_path / "packages/qgis-sdk-python/scripts/generate_bridge_clients.py"
    generator.parent.mkdir(parents=True)
    generator.write_text("print('generator ran')\n", encoding="utf-8")
    (tmp_path / "examples/simple").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
        cwd=tmp_path,
        check=True,
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    pixi = bindir / "pixi"
    pixi.write_text("#!/bin/sh\necho reference-check-ran\n", encoding="utf-8")
    pixi.chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    run = lambda: subprocess.run(
        [sys.executable, str(script), "check-generated"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    clean = run()
    assert clean.returncode == 0 and "reference-check-ran" in clean.stdout
    changed = tmp_path / "packages/qgis-sdk-typescript/src/generated/new.ts"
    changed.parent.mkdir(parents=True)
    changed.write_text("new\n", encoding="utf-8")
    stale = run()
    assert stale.returncode == 1 and "generated client is stale" in stale.stdout
    assert "reference-check-ran" not in stale.stdout
    changed.unlink()
    pixi.write_text("#!/bin/sh\necho reference-failed\nexit 7\n", encoding="utf-8")
    bad_reference = run()
    assert bad_reference.returncode == 7 and "reference-failed" in bad_reference.stdout
    generator.write_text("import sys\nsys.exit(4)\n", encoding="utf-8")
    bad_generator = run()
    assert bad_generator.returncode == 4
    assert "reference-failed" not in bad_generator.stdout


@pytest.fixture
def generated_repo(tmp_path: Path) -> Path:
    """A committed Git tree with the real generator and its actual dependencies."""
    root = SCRIPT.parents[1]
    for directory in (
        "packages/qgis-sdk-runtime/src",
        "packages/qgis-sdk-tools/src",
        "packages/qgis-sdk-python/tests/contract_sample",
    ):
        shutil.copytree(
            root / directory,
            tmp_path / directory,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    for filename in (
        "automation/ci.py",
        "packages/qgis-sdk-python/scripts/generate_bridge_clients.py",
        "packages/qgis-sdk-typescript/src/generated/host.ts",
        "packages/qgis-sdk-typescript/tests/contracts/generated/clients/sites.ts",
        "packages/qgis-sdk-typescript/tests/contracts/generated/clients/sites.schema.ts",
    ):
        target = tmp_path / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / filename, target)
    (tmp_path / "examples/simple").mkdir(parents=True)
    other_generated = (
        tmp_path
        / "packages/qgis-sdk-typescript/tests/contracts/generated/clients/other.ts"
    )
    other_generated.write_text(
        "// Generated by qgis-sdk. Do not edit.\n// Source: the declarations of another.plugin.\n",
        encoding="utf-8",
    )
    outside = tmp_path / "packages/qgis-sdk-typescript/other/sites.ts"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(
        (
            tmp_path
            / "packages/qgis-sdk-typescript/tests/contracts/generated/clients/sites.ts"
        ).read_bytes()
    )
    other = tmp_path / "packages/qgis-sdk-typescript/src/generated/unrelated.ts"
    other.write_text("// An unrelated manually maintained file.\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
        cwd=tmp_path,
        check=True,
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    pixi = bindir / "pixi"
    pixi.write_text("#!/bin/sh\necho reference-check-ran\n", encoding="utf-8")
    pixi.chmod(0o755)
    return tmp_path


def run_real_generated_gate(root: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": f"{root / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(
        [sys.executable, str(root / "automation/ci.py"), "check-generated"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_real_generated_gate_detects_a_stopped_artifact_without_deleting_files(
    generated_repo: Path,
):
    clean = run_real_generated_gate(generated_repo)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "reference-check-ran" in clean.stdout
    old = (
        generated_repo
        / "packages/qgis-sdk-typescript/tests/contracts/generated/clients/sites.ts"
    )
    old_bytes = old.read_bytes()
    unrelated = [
        generated_repo / "packages/qgis-sdk-typescript/src/generated/unrelated.ts",
        old.parent / "other.ts",
        generated_repo / "packages/qgis-sdk-typescript/other/sites.ts",
    ]
    unrelated_bytes = {path: path.read_bytes() for path in unrelated}
    generator = (
        generated_repo / "packages/qgis-sdk-python/scripts/generate_bridge_clients.py"
    )
    contents = generator.read_text(encoding="utf-8")
    entry = """        (
            PLUGIN_CLIENT_PATH,
            describe(sites_app).to_dict(),
            generate_typescript,
        ),
"""
    assert contents.count(entry) == 1
    generator.write_text(contents.replace(entry, ""), encoding="utf-8")
    stopped = run_real_generated_gate(generated_repo)
    assert stopped.returncode != 0, stopped.stdout + stopped.stderr
    assert "sites.ts" in stopped.stdout + stopped.stderr
    assert "orphan" in (stopped.stdout + stopped.stderr).lower()
    assert "::error title=generated client is stale::" in stopped.stdout
    assert "reference-check-ran" not in stopped.stdout
    assert old.read_bytes() == old_bytes
    assert {path: path.read_bytes() for path in unrelated} == unrelated_bytes


@pytest.mark.parametrize(
    ("entry", "relative"),
    [
        (
            """        (
            PLUGIN_SCHEMA_PATH,
            describe(sites_app).to_dict(),
            generate_sample_schema,
        ),
""",
            "packages/qgis-sdk-typescript/tests/contracts/generated/clients/sites.schema.ts",
        ),
        (
            "        (HOST_CLIENT_PATH, host_description(), generate_host_typescript),\n",
            "packages/qgis-sdk-typescript/src/generated/host.ts",
        ),
    ],
)
def test_gate_detects_each_other_stopped_owned_artifact(
    generated_repo: Path,
    entry: str,
    relative: str,
):
    generator = (
        generated_repo / "packages/qgis-sdk-python/scripts/generate_bridge_clients.py"
    )
    contents = generator.read_text(encoding="utf-8")
    assert contents.count(entry) == 1
    generator.write_text(contents.replace(entry, ""), encoding="utf-8")
    old = generated_repo / relative
    before = old.read_bytes()
    result = run_real_generated_gate(generated_repo)
    assert result.returncode == 1
    assert "orphaned" in result.stderr and old.name in result.stderr
    assert old.read_bytes() == before


@pytest.mark.parametrize("change", ["changed", "removed"])
def test_real_generated_gate_rejects_committed_drift_and_missing_files(
    generated_repo: Path,
    change: str,
):
    relative = "packages/qgis-sdk-typescript/tests/contracts/generated/clients/sites.ts"
    path = generated_repo / relative
    if change == "changed":
        path.write_text("stale contents\n", encoding="utf-8")
        subprocess.run(["git", "add", relative], cwd=generated_repo, check=True)
    else:
        subprocess.run(["git", "rm", "-q", relative], cwd=generated_repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "drift",
        ],
        cwd=generated_repo,
        check=True,
    )
    result = run_real_generated_gate(generated_repo)
    assert result.returncode == 1
    assert "generated client is stale" in result.stdout
    assert "generate_bridge_clients.py" in result.stdout
    assert "reference-check-ran" not in result.stdout
    assert path.read_bytes() == (SCRIPT.parents[1] / relative).read_bytes()


def test_real_generated_gate_reports_renamed_output_and_leaves_old_file(
    generated_repo: Path,
):
    generator = (
        generated_repo / "packages/qgis-sdk-python/scripts/generate_bridge_clients.py"
    )
    contents = generator.read_text(encoding="utf-8")
    assert contents.count(' / "sites.ts"') == 1
    generator.write_text(
        contents.replace(' / "sites.ts"', ' / "renamed.ts"'), encoding="utf-8"
    )
    old = (
        generated_repo
        / "packages/qgis-sdk-typescript/tests/contracts/generated/clients/sites.ts"
    )
    before = old.read_bytes()
    result = run_real_generated_gate(generated_repo)
    assert result.returncode == 1
    assert "orphaned" in result.stderr and "sites.ts" in result.stderr
    assert "reference-check-ran" not in result.stdout
    assert old.read_bytes() == before
    assert (old.parent / "renamed.ts").is_file()


def test_generator_check_mode_detects_orphans_without_writing(generated_repo: Path):
    generator = (
        generated_repo / "packages/qgis-sdk-python/scripts/generate_bridge_clients.py"
    )
    contents = generator.read_text(encoding="utf-8")
    assert contents.count(' / "sites.ts"') == 1
    generator.write_text(
        contents.replace(' / "sites.ts"', ' / "renamed.ts"'), encoding="utf-8"
    )
    old = (
        generated_repo
        / "packages/qgis-sdk-typescript/tests/contracts/generated/clients/sites.ts"
    )
    before = old.read_bytes()
    result = subprocess.run(
        [sys.executable, str(generator), "--check"],
        cwd=generated_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "orphaned" in result.stderr and "sites.ts" in result.stderr
    assert old.read_bytes() == before
    assert not (old.parent / "renamed.ts").exists()


def test_missing_command_returns_shell_status_and_records_error(tmp_path: Path):
    result = run_ci(
        "run-log", "missing.log", "--", "nonexistent-ci-command-782", cwd=tmp_path
    )
    assert result.returncode == 127
    assert "nonexistent-ci-command-782" in (tmp_path / "missing.log").read_text()


def test_native_exit_five_without_an_expected_skip_is_a_failure(tmp_path: Path):
    result = run_ci(
        "native",
        "--",
        sys.executable,
        "-c",
        "import sys; print('no tests ran'); sys.exit(5)",
        cwd=tmp_path,
    )
    assert result.returncode == 5
    assert "::error title=native layers: pytest::" in result.stdout
    assert "::warning::native layers did not run" not in result.stdout


def test_bun_ui_build_order_and_tests_with_fake_bun(tmp_path: Path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "bun"
    stub.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$BUN_CALLS"\n'
        'if [ "$1" = test ]; then echo "113 pass" >&2; fi\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    calls = tmp_path / "calls.txt"
    result = run_ci(
        "bun-ui",
        cwd=tmp_path,
        env={
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            "BUN_CALLS": str(calls),
        },
    )
    assert result.returncode == 0
    assert calls.read_text().splitlines() == [
        "run --filter @archont561/qgis-sdk build",
        "run --filter @archont561/qgis-sdk-ui build",
        "test --conditions=browser packages/qgis-sdk-ui/tests packages/qgis-sdk-ui-alias/tests",
    ]
    assert "113 pass" in (tmp_path / "bun-ui-tests.log").read_text()


def test_ci_workflow_calls_helpers_and_keeps_gates():
    import yaml

    workflow = yaml.safe_load(
        (SCRIPT.parents[1] / ".github/workflows/ci.yml").read_text()
    )
    jobs = workflow["jobs"]
    checks = {step.get("name"): step for step in jobs["linux"]["steps"]}
    coverage = {step.get("name"): step for step in jobs["coverage"]["steps"]}
    assert "needs" not in jobs["linux"] and "needs" not in jobs["coverage"]
    aggregate = jobs["checks"]
    assert set(aggregate["needs"]) == {"linux", "coverage", "lts"}
    assert aggregate["if"] == "${{ always() }}"
    gate = aggregate["steps"][-1]
    assert gate["if"] == (
        "${{ needs.linux.result != 'success' || needs.coverage.result != 'success'"
        " || needs.lts.result != 'success' }}"
    )
    assert gate["run"] == "exit 1"
    for name in ("linux", "coverage"):
        steps = {step.get("name"): step for step in jobs[name]["steps"]}
        assert steps["Set up Pixi"]["with"]["locked"] is True
        assert steps["Set up Pixi"]["with"]["cache"] is True
        assert (
            steps["Install JavaScript dependencies"]["run"]
            == "pixi run -e default automation -- install_js"
        )
        assert steps["Report the failed step"]["if"] == "failure()"
        assert steps["Report the failed step"]["env"]["STEPS"] == "${{ toJSON(steps) }}"
    expected_checks = {
        "Check commit messages": "pixi run -e default automation -- check_commits",
        "Lint Python": "pixi run -e default automation -- lint_python",
        "Check Python formatting": "pixi run -e default automation -- format_check",
        "Test release tooling": "pixi run -e default automation -- test_scripts",
        "Verify the scoped versions and the shared contract": "pixi run -e default automation -- release_verify_versions",
        "Check the generated bridge clients are current": "pixi run -e default automation -- check_generated",
        "Check the Processing snapshot is current": "pixi run -e default python packages/qgis-sdk-python/scripts/generate_processing_snapshot.py --check",
        "Test the reference plugin through qgis-sdk test": "pixi run -e default automation -- reference_example",
        "Test the reference page on the workspace bridge": "pixi run -e default automation -- test_reference_web",
        "Lint and format TypeScript": "pixi run -e default automation -- biome",
        "Lint GitHub Actions": "pixi run -e default automation -- lint_actions",
        "Check repository policy": "pixi run -e default automation -- lint_repository",
        "Test repository policy": "pixi run -e default automation -- test_alint_policy",
        "Typecheck TypeScript": "pixi run -e default automation -- typecheck",
        "Build the qgis-sdk-ui Storybook": "pixi run -e default automation -- storybook",
    }
    for name, command in expected_checks.items():
        assert checks[name]["run"] == command
    assert checks["Checkout"]["with"]["fetch-depth"] == 0
    assert (
        checks["Compute commit range"]["env"]["BASE_SHA"]
        == "${{ github.event.pull_request.base.sha || github.event.before }}"
    )
    assert (
        checks["Test the native layers offscreen"]["run"]
        == "pixi run -e default automation -- native"
    )
    assert checks["Test the native layers offscreen"]["env"] == {
        "QT_QPA_PLATFORM": "offscreen",
        "QGIS_SDK_NATIVE_SERVICES": "1",
    }
    lts = {step.get("name"): step for step in jobs["lts"]["steps"]}
    assert jobs["lts"]["runs-on"] == "ubuntu-24.04"
    assert "needs" not in jobs["lts"]
    assert (
        "qgis qgis-server python3-qgis"
        in lts["Install the QGIS 3.44 LTS packages"]["run"]
    )
    assert (
        "--system-site-packages"
        in lts["Install the SDK over the system bindings"]["run"]
    )
    assert (
        lts["Test both hosts on the LTS"]["run"]
        == ".venv-lts/bin/python -m automation.ci lts"
    )
    assert lts["Test both hosts on the LTS"]["env"] == {
        "QT_QPA_PLATFORM": "offscreen",
        # The dev-loop harness starts a real QgsServer, so the row opts it in.
        "QGIS_SDK_SERVER_DEV": "1",
    }
    assert coverage["Check coverage for all packages"]["id"] == "coverage"
    assert (
        coverage["Check coverage for all packages"]["run"]
        == "pixi run -e default automation -- coverage"
    )
    assert (
        coverage["Annotate the coverage failure"]["if"]
        == "failure() && steps.coverage.outcome == 'failure'"
    )
    for name, path, flag in (
        (
            "Upload Python coverage",
            "packages/qgis-sdk-python/coverage/lcov.info",
            "qgis-sdk-python",
        ),
        (
            "Upload TypeScript coverage",
            "coverage/qgis-sdk-typescript/lcov.info",
            "qgis-sdk-typescript",
        ),
        ("Upload UI coverage", "coverage/qgis-sdk-ui/lcov.info", "qgis-sdk-ui"),
    ):
        assert (
            coverage[name]["if"]
            == "${{ !cancelled() && steps.coverage.outcome == 'success' }}"
        )
        assert coverage[name]["with"]["files"] == path
        assert coverage[name]["with"]["flags"] == flag
        assert coverage[name]["with"]["fail_ci_if_error"] is True
    assert jobs["cross-platform"]["if"] == "${{ github.event_name != 'push' }}"
    assert "needs" not in jobs["cross-platform"]
    assert checks["Report the failed step"]["env"]["STEPS"] == "${{ toJSON(steps) }}"
    cross = {step.get("name"): step for step in jobs["cross-platform"]["steps"]}
    assert "run-log bun-tests.log" in cross["Test TypeScript bridge"]["run"]
    assert cross["Test qgis-sdk-ui"]["run"] == "python -m automation.ci bun-ui"
    assert "report-bun bun-tests.log" in cross["Report TypeScript test results"]["run"]
    assert (
        "report-bun bun-ui-tests.log" in cross["Report qgis-sdk-ui test results"]["run"]
    )


def test_bun_ui_stops_if_a_build_fails(tmp_path: Path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "bun"
    stub.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$BUN_CALLS"\nexit 9\n', encoding="utf-8"
    )
    stub.chmod(0o755)
    calls = tmp_path / "calls.txt"
    result = run_ci(
        "bun-ui",
        cwd=tmp_path,
        env={
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            "BUN_CALLS": str(calls),
        },
    )
    assert result.returncode == 9
    assert calls.read_text().splitlines() == ["run --filter @archont561/qgis-sdk build"]
    assert not (tmp_path / "bun-ui-tests.log").exists()


def test_skill_tests_are_not_run_or_trigger_ci():
    import tomllib

    import yaml

    root = SCRIPT.parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    for event in ("push", "pull_request"):
        assert ".agents/skills/**" in workflow[True][event]["paths-ignore"]
    steps = [step for job in workflow["jobs"].values() for step in job["steps"]]
    assert not any("skill" in step.get("name", "").lower() for step in steps)
    assert not any(".agents/skills" in step.get("run", "") for step in steps)
    pixi = tomllib.loads((root / "pixi.toml").read_text())
    assert "test-skill-creator" not in pixi["feature"]["python"]["tasks"]
    python_package = json.loads(
        (root / "packages/qgis-sdk-python/package.json").read_text()
    )
    assert ".agents/skills" not in python_package["scripts"]["test"]
    assert not (root / ".agents/skills/skill-creator/tests").exists()


# -- Gherkin linting ---------------------------------------------------------

FEATURES_ROOT = "packages/qgis-sdk-python/tests/features"


def _checkout(tmp_path: Path, feature: str = "Feature: A\n\n  Scenario: B\n") -> Path:
    """A throwaway checkout with one feature file where the lint looks."""
    directory = tmp_path / FEATURES_ROOT
    directory.mkdir(parents=True)
    (directory / "sample.feature").write_text(feature, encoding="utf-8")
    return tmp_path


def _stub(tmp_path: Path, reported: str = "", status: int = 0) -> Path:
    """A stand-in for gherlint: it prints ``reported`` and exits ``status``."""
    stub = tmp_path / "gherlint"
    stub.write_text(
        f"#!/bin/sh\ncat <<'REPORT'\n{reported}\nREPORT\nexit {status}\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def test_check_gherkin_passes_a_file_the_linter_does_not_complain_about(
    tmp_path: Path,
):
    root = _checkout(tmp_path)
    result = run_ci(
        "check-gherkin",
        "--root",
        str(root),
        "--gherlint",
        str(_stub(tmp_path)),
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "1 feature file(s) clean" in result.stdout


def test_check_gherkin_fails_on_a_finding_even_though_the_linter_exits_zero(
    tmp_path: Path,
):
    """gherlint always exits zero, so the findings are counted from its report."""
    root = _checkout(tmp_path)
    finding = (
        f"{root / FEATURES_ROOT / 'sample.feature'}:3:3: "
        "Scenario does not contain any When step (missing-when-step)"
    )
    stub = _stub(tmp_path, reported=f"************* sample.feature\n{finding}")
    result = run_ci(
        "check-gherkin", "--root", str(root), "--gherlint", str(stub), cwd=tmp_path
    )
    assert result.returncode == 1
    assert "missing-when-step" in result.stdout
    assert "1 finding(s)" in result.stdout


def test_check_gherkin_fails_when_a_feature_file_sits_outside_the_lint(
    tmp_path: Path,
):
    root = _checkout(tmp_path)
    elsewhere = root / "packages" / "elsewhere"
    elsewhere.mkdir(parents=True)
    (elsewhere / "stray.feature").write_text("Feature: Stray\n", encoding="utf-8")
    result = run_ci(
        "check-gherkin",
        "--root",
        str(root),
        "--gherlint",
        str(_stub(tmp_path)),
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert "stray.feature is outside the linted directories" in result.stdout
    assert "FEATURE_DIRECTORIES" in result.stdout


def test_check_gherkin_reports_a_missing_linter_rather_than_passing(tmp_path: Path):
    root = _checkout(tmp_path)
    result = run_ci(
        "check-gherkin",
        "--root",
        str(root),
        "--gherlint",
        str(tmp_path / "no-such-gherlint"),
        cwd=tmp_path,
    )
    assert result.returncode == 127
    assert "gherlint is missing" in result.stdout


def test_check_gherkin_fails_when_the_linter_itself_fails(tmp_path: Path):
    root = _checkout(tmp_path)
    result = run_ci(
        "check-gherkin",
        "--root",
        str(root),
        "--gherlint",
        str(_stub(tmp_path, reported="boom", status=3)),
        cwd=tmp_path,
    )
    assert result.returncode == 3
    assert "gherlint exited with 3" in result.stdout


def test_every_feature_file_in_the_checkout_is_linted():
    """The invariant behind the checks: no scenario escapes the linted tree."""
    from automation import ci

    root = SCRIPT.parents[1]
    files = ci.feature_files(root)
    assert files, "the checkout has no feature file; the lint would pass vacuously"
    assert ci.unlinted_features(root) == []
    assert all(
        str(path.relative_to(root)).startswith(ci.FEATURE_DIRECTORIES) for path in files
    )


def test_the_linter_policy_file_is_where_the_linter_reads_it():
    """`gherlint` reads `gherlint.toml` from the working directory it is run in."""
    root = SCRIPT.parents[1]
    policy = root / "gherlint.toml"
    assert policy.is_file()
    import tomllib

    disabled = tomllib.loads(policy.read_text(encoding="utf-8"))["reporting"]["disable"]
    # Exactly the one message the Background rule cannot satisfy both ways.
    assert disabled == ["missing-given-step"]
