"""End-to-end CLI behaviour with injected git, files, and GitHub fakes."""

import json

from conftest import SAMPLE_VERSIONRC
from qgis_sdk_release import artifacts, cli, github, gitops

PYPROJECT = '[project]\nname = "qgis-sdk"\nversion = "0.1.0"\n'
PACKAGE_JSON = '{\n\t"name": "qgis-sdk-bridge",\n\t"version": "0.1.0"\n}\n'


def _versionrc(tmp_path):
    path = tmp_path / ".versionrc"
    path.write_text(SAMPLE_VERSIONRC, encoding="utf-8")
    return path


def _fake_git(monkeypatch, tags=(), log=""):
    monkeypatch.setattr(gitops, "list_tags", lambda runner=None: tuple(tags))
    monkeypatch.setattr(gitops, "log_commits", lambda rng=None, runner=None: log)


def test_plan_dispatch_writes_outputs_and_changelog(tmp_path, monkeypatch):
    config = _versionrc(tmp_path)
    out_file = tmp_path / "gh_output"
    out_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    _fake_git(monkeypatch, log="a" * 40 + "\x1f" + "feat: x" + "\x1f" + "\x1e\n")
    assert (
        cli.main(["plan", "--trigger", "dispatch", "--config", str(config), "--json"])
        == 0
    )
    outputs = dict(
        line.split("=", 1) for line in out_file.read_text().splitlines() if line
    )
    assert outputs["action"] == "tag"
    assert outputs["tag"] == "v0.1.0"
    assert outputs["prerelease"] == "false"
    changelog = (tmp_path / "qgis-sdk-release-changelog.md").read_text()
    assert "## v0.1.0" in changelog
    assert outputs["changelog_file"].endswith("qgis-sdk-release-changelog.md")


def test_plan_push_without_tags_skips(tmp_path, monkeypatch):
    config = _versionrc(tmp_path)
    _fake_git(monkeypatch)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert cli.main(["plan", "--config", str(config)]) == 0


def test_classify_reports_prerelease(tmp_path, monkeypatch):
    out_file = tmp_path / "gh_output"
    out_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    assert cli.main(["classify", "--tag", "v0.1.0-rc.1"]) == 0
    outputs = dict(
        line.split("=", 1) for line in out_file.read_text().splitlines() if line
    )
    assert outputs == {
        "version": "0.1.0-rc.1",
        "pep440": "0.1.0rc1",
        "prerelease": "true",
    }


def test_classify_rejects_bad_tag():
    assert cli.main(["classify", "--tag", "0.1.0"]) == 1


def test_tag_creates_and_pushes_with_message_file(tmp_path, monkeypatch):
    message = tmp_path / "changelog.md"
    message.write_text("# Changelog\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(gitops, "create_tag", lambda *a, **k: calls.append((a, k)))
    assert (
        cli.main(["tag", "--tag", "v0.1.0", "--message-file", str(message), "--push"])
        == 0
    )
    (args, kwargs) = calls[0]
    assert args == ("v0.1.0", "# Changelog\n")
    assert kwargs == {"push": True}


def test_tag_needs_a_message():
    assert cli.main(["tag", "--tag", "v0.1.0"]) == 1


def test_stamp_rewrites_both_manifests(tmp_path, monkeypatch):
    pyproject = tmp_path / "pyproject.toml"
    package = tmp_path / "package.json"
    pyproject.write_text(PYPROJECT, encoding="utf-8")
    package.write_text(PACKAGE_JSON, encoding="utf-8")
    monkeypatch.setattr(cli, "_PYPROJECT", pyproject)
    monkeypatch.setattr(cli, "_BRIDGE_PACKAGE", package)
    assert cli.main(["stamp", "--version", "0.2.0-rc.1"]) == 0
    assert 'version = "0.2.0rc1"' in pyproject.read_text()
    assert '"version": "0.2.0-rc.1"' in package.read_text()


def test_build_python_builds_then_checks(tmp_path, monkeypatch):
    built = []
    checked = []

    def fake_build(package, outdir, runner=None):
        built.append((package, str(outdir)))
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "qgis_sdk-0.1.0-py3-none-any.whl").write_bytes(b"x")

    monkeypatch.setattr(artifacts, "build_wheel", fake_build)
    monkeypatch.setattr(
        artifacts, "twine_check", lambda wheels, runner=None: checked.append(wheels)
    )
    outdir = tmp_path / "dist" / "pypi"
    assert (
        cli.main(
            ["build-python", "--package", "packages/qgis-sdk", "--outdir", str(outdir)]
        )
        == 0
    )
    assert built == [("packages/qgis-sdk", str(outdir))]
    assert [wheel.name for wheel in checked[0]] == ["qgis_sdk-0.1.0-py3-none-any.whl"]


def test_build_python_fails_without_a_wheel(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "build_wheel", lambda *a, **k: None)
    assert cli.main(["build-python", "--outdir", str(tmp_path / "empty")]) == 1


def test_checksums_writes_sums_file(tmp_path):
    asset = tmp_path / "a.whl"
    asset.write_bytes(b"data")
    out = tmp_path / "SHA256SUMS"
    assert cli.main(["checksums", "--out", str(out), str(asset)]) == 0
    lines = out.read_text().splitlines()
    assert len(lines) == 1 and lines[0].endswith("  a.whl")


def test_github_release_publishes_prerelease_with_assets(tmp_path, monkeypatch):
    body = tmp_path / "notes.md"
    body.write_text("# Changelog\n", encoding="utf-8")
    wheel = tmp_path / "qgis_sdk-0.1.0rc1-py3-none-any.whl"
    wheel.write_bytes(b"w")
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("00  wheel\n", encoding="utf-8")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    created = []
    uploaded = []
    monkeypatch.setattr(
        github,
        "create_release",
        lambda slug, token, tag, name, text, prerelease, opener=None: (
            created.append((slug, tag, text, prerelease))
            or {"upload_url": "https://u{?name}", "html_url": "https://html"}
        ),
    )
    monkeypatch.setattr(
        github,
        "upload_asset",
        lambda url, token, path, opener=None: uploaded.append(path),
    )
    assert (
        cli.main(
            [
                "github-release",
                "--tag",
                "v0.1.0-rc.1",
                "--body-file",
                str(body),
                "--asset",
                str(wheel),
                str(sums),
            ]
        )
        == 0
    )
    assert created == [("owner/repo", "v0.1.0-rc.1", "# Changelog\n", True)]
    assert uploaded == [wheel, sums]
    assert "https://html" in summary.read_text()


def test_github_release_needs_repo_and_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert cli.main(["github-release", "--tag", "v0.1.0"]) == 1


def test_plan_json_output_is_valid_json(tmp_path, monkeypatch, capsys):
    config = _versionrc(tmp_path)
    _fake_git(
        monkeypatch,
        tags=("v0.1.0",),
        log="a" * 40 + "\x1f" + "feat: x" + "\x1f" + "\x1e\n",
    )
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    assert cli.main(["plan", "--config", str(config), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tag"] == "v0.2.0"
    assert payload["base_tag"] == "v0.1.0"
    changelog = (tmp_path / "qgis-sdk-release-changelog.md").read_text()
    assert "owner/repo/compare/v0.1.0...v0.2.0" in changelog
