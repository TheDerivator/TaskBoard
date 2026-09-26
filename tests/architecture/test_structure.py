"""Layer contracts hold, the code map is fresh, and app.py stays a thin entrypoint."""

import importlib.util
from pathlib import Path
from types import ModuleType

from importlinter.cli import lint_imports

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_contracts_hold() -> None:
    """The contracts live in pyproject.toml ([tool.importlinter])."""
    assert lint_imports(config_filename=str(ROOT / "pyproject.toml"), no_cache=True) == 0


def test_codemap_is_up_to_date() -> None:
    codemap = _load_script("gen_codemap")
    current = (ROOT / "docs" / "CODEMAP.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert current == codemap.render(), "run `uv run python scripts/gen_codemap.py`"


def test_every_source_file_has_a_summary() -> None:
    """The code map is only useful if every file describes itself (vendored code excepted)."""
    codemap = _load_script("gen_codemap")
    missing = [
        str(path.relative_to(ROOT))
        for folder in ("taskboard", "tests", "scripts")
        for pattern in ("*.py", "*.js", "*.mjs", "*.css", "*.html")
        for path in (ROOT / folder).rglob(pattern)
        if not {"__pycache__", "vendor"} & set(path.parts) and not codemap.summarize(path)
    ]
    assert missing == []


def test_entrypoint_stays_thin() -> None:
    code_lines = [
        line
        for line in (ROOT / "app.py").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith(("#", '"""'))
    ]
    assert len(code_lines) <= 3, "app.py only wires the app: put logic in the taskboard package"
