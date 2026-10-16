from __future__ import annotations

from pathlib import Path
from types import ModuleType


def test_embed_file_preserves_file_specific_output_shapes(
    tmp_path: Path, review_module: ModuleType
) -> None:
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello", encoding="utf-8")
    image_file = tmp_path / "map.png"
    image_file.write_bytes(b"image")
    pdf_file = tmp_path / "report.pdf"
    pdf_file.write_bytes(b"pdf")
    spreadsheet = tmp_path / "table.xlsx"
    spreadsheet.write_bytes(b"sheet")
    binary_file = tmp_path / "data.bin"
    binary_file.write_bytes(b"binary")

    assert review_module.embed_file(text_file) == {
        "name": "notes.txt",
        "type": "text",
        "content": "hello",
    }
    assert review_module.embed_file(image_file)["data_uri"].startswith(
        "data:image/png;base64,"
    )
    assert review_module.embed_file(pdf_file) == {
        "name": "report.pdf",
        "type": "pdf",
        "data_uri": "data:application/pdf;base64,cGRm",
    }
    assert review_module.embed_file(spreadsheet) == {
        "name": "table.xlsx",
        "type": "xlsx",
        "data_b64": "c2hlZXQ=",
    }
    assert review_module.embed_file(binary_file)["type"] == "binary"


def test_optional_json_loader_handles_missing_invalid_and_valid_files(
    tmp_path: Path, review_module: ModuleType
) -> None:
    missing = tmp_path / "missing.json"
    assert review_module._load_optional_json(missing) is None

    malformed = tmp_path / "malformed.json"
    malformed.write_text("not-json", encoding="utf-8")
    assert review_module._load_optional_json(malformed) is None

    valid = tmp_path / "valid.json"
    valid.write_text('{"summary": {"passed": 1}}', encoding="utf-8")
    assert review_module._load_optional_json(valid) == {"summary": {"passed": 1}}


def test_failed_binary_read_uses_the_existing_error_shape(
    tmp_path: Path, review_module: ModuleType
) -> None:
    missing_file = tmp_path / "missing.png"

    assert review_module.embed_file(missing_file) == {
        "name": "missing.png",
        "type": "error",
        "content": "(Error reading file)",
    }


def test_build_run_preserves_an_empty_grading_object(
    tmp_path: Path, review_module: ModuleType
) -> None:
    run_dir = tmp_path / "eval-1" / "with_skill" / "run-1"
    (run_dir / "outputs").mkdir(parents=True)
    (run_dir / "grading.json").write_text("{}", encoding="utf-8")

    result = review_module.build_run(tmp_path, run_dir)

    assert result["grading"] == {}


def test_build_run_collects_prompt_outputs_and_grading(
    tmp_path: Path, review_module: ModuleType
) -> None:
    run_dir = tmp_path / "eval-1" / "with_skill" / "run-1"
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True)
    (run_dir / "eval_metadata.json").write_text(
        '{"prompt": "make a map", "eval_id": 1}', encoding="utf-8"
    )
    (run_dir / "grading.json").write_text(
        '{"summary": {"passed": 1}}', encoding="utf-8"
    )
    (outputs_dir / "result.txt").write_text("ready", encoding="utf-8")
    (outputs_dir / "transcript.md").write_text("hidden metadata", encoding="utf-8")

    result = review_module.build_run(tmp_path, run_dir)

    assert result is not None
    assert result["prompt"] == "make a map"
    assert result["eval_id"] == 1
    assert result["grading"] == {"summary": {"passed": 1}}
    assert [item["name"] for item in result["outputs"]] == ["result.txt"]
