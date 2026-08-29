import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PREFIXES = (
    "adapters",
    "broker",
    "trading",
    "volcanoes.execution",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_global_rotation_package_has_no_execution_or_broker_dependency():
    for path in (ROOT / "global_rotation").glob("*.py"):
        imports = _imports(path)
        assert not any(
            name.startswith(FORBIDDEN_PREFIXES) for name in imports
        ), f"Unsafe dependency in {path}: {sorted(imports)}"


def test_daily_runner_contains_no_order_submission_call():
    source = (ROOT / "scripts/run_global_rotation_daily.py").read_text(encoding="utf-8")

    assert "submit_bracket_order" not in source
    assert "submit_paper_order" not in source
    assert "orders_submitted" not in source
