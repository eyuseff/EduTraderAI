from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = PROJECT_ROOT / "spikes/execution_durability"
PRODUCTION_RUNTIME_PATHS = (
    PROJECT_ROOT / "app.py",
    PROJECT_ROOT / "adapters/paper_order_preview.py",
    PROJECT_ROOT / "adapters/paper_order_submission.py",
    PROJECT_ROOT / "adapters/scanner_execution.py",
    PROJECT_ROOT / "engine/supervised_brain.py",
    PROJECT_ROOT / "engine/brain.py",
    PROJECT_ROOT / "scanner_engine/automated_scanner.py",
)


def test_spike_code_has_no_broker_or_runtime_imports() -> None:
    forbidden_roots = {
        "broker",
        "adapters",
        "scanner_engine",
        "engine",
        "trading",
        "streamlit",
    }
    offenders: list[str] = []
    for path in SPIKE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden_roots:
                        offenders.append(f"{path}: imports {alias.name}")
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in forbidden_roots:
                    offenders.append(f"{path}: imports {node.module}")

    assert offenders == []


def test_spike_code_does_not_access_production_state_or_credentials() -> None:
    prohibited = (
        "state/simulated_broker.json",
        "simulated_broker",
        "TradingClient",
        "submit_order",
        "cancel_order",
        "API_KEY",
        "SECRET",
        "TOKEN",
        "PASSWORD",
    )
    offenders = []
    for path in SPIKE_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path} contains {token}" for token in prohibited if token in source
        )

    assert offenders == []


def test_runtime_entry_points_do_not_import_spike_code() -> None:
    offenders = []
    for path in PRODUCTION_RUNTIME_PATHS:
        source = path.read_text(encoding="utf-8")
        if "spikes.execution_durability" in source:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []
