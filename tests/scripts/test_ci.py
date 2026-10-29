"""Exercise CI helper commands without a runner, QGIS, or live GitHub Actions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci.py"


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
    script = tmp_path / "scripts/ci.py"
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
    assert set(aggregate["needs"]) == {"linux", "coverage"}
    assert aggregate["if"] == "${{ always() }}"
    gate = aggregate["steps"][-1]
    assert (
        gate["if"]
        == "${{ needs.linux.result != 'success' || needs.coverage.result != 'success' }}"
    )
    assert gate["run"] == "exit 1"
    for name in ("linux", "coverage"):
        steps = {step.get("name"): step for step in jobs[name]["steps"]}
        assert steps["Set up Pixi"]["with"]["locked"] is True
        assert steps["Set up Pixi"]["with"]["cache"] is True
        assert (
            steps["Install JavaScript dependencies"]["run"]
            == "pixi run -e bun install-js"
        )
        assert steps["Report the failed step"]["if"] == "failure()"
        assert steps["Report the failed step"]["env"]["STEPS"] == "${{ toJSON(steps) }}"
    expected_checks = {
        "Check commit messages": "pixi run -e default check-commits",
        "Lint Python": "pixi run -e default lint-python",
        "Check Python formatting": "pixi run -e default format-python-check",
        "Test release tooling": "pixi run -e default test-release-tool",
        "Verify the scoped versions and the shared contract": "pixi run -e default release-verify-versions",
        "Check the generated bridge clients are current": "python scripts/ci.py check-generated",
        "Check the Processing snapshot is current": "pixi run -e default python packages/qgis-sdk-python/scripts/generate_processing_snapshot.py --check",
        "Test the reference plugin through qgis-sdk test": "pixi run -e default test-reference-example",
        "Test the reference page on the workspace bridge": "pixi run -e bun test-reference-web",
        "Lint and format TypeScript": "pixi run -e bun biome-check",
        "Lint GitHub Actions": "pixi run -e default lint-github-actions",
        "Check repository policy": "pixi run -e default lint-repository",
        "Test repository policy": "pixi run -e default test-alint-policy",
        "Typecheck TypeScript": "pixi run -e bun typecheck",
        "Build the qgis-sdk-ui Storybook": "pixi run -e bun storybook-build",
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
        == "pixi run -e default python scripts/ci.py native"
    )
    assert checks["Test the native layers offscreen"]["env"] == {
        "QT_QPA_PLATFORM": "offscreen",
        "QGIS_SDK_NATIVE_SERVICES": "1",
    }
    assert coverage["Check coverage for all packages"]["id"] == "coverage"
    assert (
        coverage["Check coverage for all packages"]["run"]
        == "python scripts/ci.py run-log coverage-output.log -- pixi run -e bun bun run coverage"
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
    assert cross["Test qgis-sdk-ui"]["run"] == "python scripts/ci.py bun-ui"
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
