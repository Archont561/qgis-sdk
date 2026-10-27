"""``qgis-sdk processing generate``: the typed Processing catalogue of a project.

The tools never import QGIS. Reading the registry happens in the project's
QGIS install, in a subprocess running
``python -m qgis_sdk.adapters.qgis.catalogue`` (the same interpreter and
environment ``qgis-sdk test --target qgis`` uses); what comes back is a
plain catalogue JSON, and everything from there on is pure: the emitters in
:mod:`qgis_sdk.processing.codegen` render the Python package and the
TypeScript module, and this module writes or checks them exactly as
``bridge generate`` does (decision-64).
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from qgis_sdk.models import Catalogue, QgisSdkError
from qgis_sdk.processing.codegen import emit_typescript_module, render_package
from qgis_sdk.processing.snapshot import CORE_PROVIDERS

from .devtools.installs import QgisInstall, sdk_import_paths, wants_headless

__all__ = [
    "CORE_PROVIDERS",
    "DEFAULT_WEB_PATH",
    "READER_MODULE",
    "GeneratedFiles",
    "QgisSdkProcessingGenerateError",
    "check_files",
    "read_host_catalogue",
    "render_files",
    "write_files",
]

#: The runtime module the subprocess runs to write the registry as JSON.
READER_MODULE = "qgis_sdk.adapters.qgis.catalogue"
DEFAULT_WEB_PATH = Path("web/src/processing.schema.ts")
ProcessRunner = Callable[[Sequence[str], Path, Mapping[str, str] | None], int]


class QgisSdkProcessingGenerateError(QgisSdkError):
    """The catalogue could not be read or the outputs could not be produced."""


@dataclass(frozen=True, slots=True)
class GeneratedFiles:
    """Every file one generation produces, by absolute path."""

    files: Mapping[Path, str]

    def __iter__(self):
        return iter(self.files)


def read_host_catalogue(
    install: QgisInstall,
    env: Mapping[str, str],
    run_process: ProcessRunner,
    *,
    cwd: Path,
    providers: Sequence[str] | None = None,
) -> Catalogue:
    """Run the reader inside ``install`` and parse what it wrote.

    The subprocess gets the SDK's own import paths like the test runner does,
    so a project that only has the tools installed still reads its QGIS.
    """
    if install.python is None:
        raise QgisSdkProcessingGenerateError(
            f"{install.prefix} has no Python interpreter; PyQGIS only imports "
            "into the interpreter it was built for, so the catalogue cannot be read"
        )
    process_env = install.environment(
        env, extra_paths=sdk_import_paths(), headless=wants_headless(env)
    )
    with tempfile.TemporaryDirectory(prefix="qgis-sdk-catalogue-") as directory:
        out = Path(directory) / "catalogue.json"
        argv: list[str] = [str(install.python), "-m", READER_MODULE, "--out", str(out)]
        for provider in providers or ():
            argv.extend(["--provider", provider])
        code = run_process(argv, cwd, process_env)
        if code != 0:
            raise QgisSdkProcessingGenerateError(
                f"reading the Processing registry failed (exit code {code}): "
                f"{' '.join(argv)}"
            )
        if not out.exists():
            raise QgisSdkProcessingGenerateError(
                f"the reader exited 0 but wrote no catalogue at {out}"
            )
        return Catalogue.from_json(out.read_text(encoding="utf-8"))


def render_files(
    catalogue: Catalogue,
    *,
    out: Path | None,
    web_out: Path | None,
    providers: Sequence[str] | None = None,
    init: bool = True,
    package: str = "@archont561/qgis-sdk",
) -> GeneratedFiles:
    """What a generation writes: the Python package under ``out`` and the
    TypeScript module at ``web_out`` (either may be ``None``)."""
    wanted = tuple(providers) if providers else tuple(p.id for p in catalogue.providers)
    missing = [p for p in wanted if p not in {q.id for q in catalogue.providers}]
    if missing:
        raise QgisSdkProcessingGenerateError(
            f"the host has no provider {', '.join(missing)}; it holds "
            f"{', '.join(p.id for p in catalogue.providers) or 'none'}"
        )
    files: dict[Path, str] = {}
    if out is not None:
        for name, content in render_package(catalogue, wanted, init=init).items():
            files[out / name] = content
    if web_out is not None:
        files[web_out] = emit_typescript_module(catalogue, wanted, package=package)
    return GeneratedFiles(files)


def check_files(generated: GeneratedFiles) -> list[str]:
    """Messages for every file that is missing or differs from a fresh generation."""
    messages: list[str] = []
    for path, content in generated.files.items():
        if not path.exists():
            messages.append(
                f"{path} does not exist; run `qgis-sdk processing generate`"
            )
        elif path.read_text(encoding="utf-8") != content:
            messages.append(
                f"{path} is out of date; run `qgis-sdk processing generate` and "
                "commit the result"
            )
    return messages


def write_files(generated: GeneratedFiles) -> list[Path]:
    """Write every file, returning those whose content changed."""
    changed: list[Path] = []
    for path, content in generated.files.items():
        if path.exists() and path.read_text(encoding="utf-8") == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        changed.append(path)
    return changed
