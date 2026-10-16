from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

SKILL_CREATOR_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_CREATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_CREATOR_ROOT))


@pytest.fixture
def review_module() -> Iterator[ModuleType]:
    module_name = "skill_creator_review_viewer"
    module_path = SKILL_CREATOR_ROOT / "eval-viewer" / "generate_review.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(module_name, None)
