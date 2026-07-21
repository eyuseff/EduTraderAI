"""Executable dependency rules for the Preview Trade architecture."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CORE_DIRECTORIES = (
    "volcanoes/domain",
    "volcanoes/risk",
    "volcanoes/sizing",
    "volcanoes/execution",
    "volcanoes/portfolio",
    "volcanoes/analytics",
    "volcanoes/events",
)

FORBIDDEN_CORE_PREFIXES = (
    "streamlit",
    "broker",
    "trading",
    "scanner_engine",
    "engine",
    "adapters",
    "volcanoes.adapters",
)

FORBIDDEN_APPLICATION_PREFIXES = (
    "streamlit",
    "broker",
    "trading",
    "adapters",
    "volcanoes.adapters",
)

FORBIDDEN_PREVIEW_PREFIXES = (
    "streamlit",
    "sqlite3",
    "database",
    "persistence",
    "broker",
    "adapters",
    "volcanoes.adapters",
    "volcanoes.database",
    "volcanoes.persistence",
    "volcanoes.portfolio.repository",
    "volcanoes.execution.broker",
    "volcanoes.execution.paper_broker",
)

FORBIDDEN_SUBMIT_PREFIXES = (
    "streamlit",
    "adapters",
    "volcanoes.adapters",
    "broker",
    "scanner_engine",
    "database",
    "persistence",
    "volcanoes.database",
    "volcanoes.persistence",
    "engine",
    "trading.execution",
)

FORBIDDEN_SUPERVISOR_PREFIXES = (
    "streamlit",
    "adapters",
    "volcanoes.adapters",
    "broker",
    "scanner_engine",
    "database",
    "persistence",
    "volcanoes.database",
    "volcanoes.persistence",
    "engine",
    "trading",
    "volcanoes.sizing",
    "volcanoes.execution.broker",
    "volcanoes.execution.paper_broker",
    "volcanoes.execution.execution_pipeline",
    "volcanoes.execution.trade_planner",
    "volcanoes.risk.risk_manager",
)


@dataclass(frozen=True, slots=True)
class ImportReference:
    """One resolved import and its source line."""

    module: str
    line: int


def _module_identity(path: Path) -> tuple[str, bool]:
    """Return the absolute module name and whether the file is a package."""

    relative = path.relative_to(PROJECT_ROOT).with_suffix("")
    parts = list(relative.parts)
    is_package = parts[-1] == "__init__"

    if is_package:
        parts.pop()

    return ".".join(parts), is_package


def _resolve_from_base(
    *,
    current_module: str,
    is_package: bool,
    imported_module: str | None,
    level: int,
) -> str:
    """Resolve an ImportFrom node to an absolute module name."""

    if level == 0:
        return imported_module or ""

    package = current_module if is_package else current_module.rpartition(".")[0]
    package_parts = package.split(".") if package else []
    parents_to_drop = level - 1

    if parents_to_drop > len(package_parts):
        return imported_module or ""

    anchor = package_parts[: len(package_parts) - parents_to_drop]

    if imported_module:
        anchor.extend(imported_module.split("."))

    return ".".join(anchor)


def _resolved_imports(
    source: str,
    *,
    current_module: str,
    is_package: bool = False,
) -> tuple[ImportReference, ...]:
    """Parse source and return absolute import references."""

    references: list[ImportReference] = []

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            references.extend(
                ImportReference(alias.name, node.lineno) for alias in node.names
            )
            continue

        if not isinstance(node, ast.ImportFrom):
            continue

        base = _resolve_from_base(
            current_module=current_module,
            is_package=is_package,
            imported_module=node.module,
            level=node.level,
        )

        if base:
            references.append(ImportReference(base, node.lineno))

        for alias in node.names:
            if alias.name == "*":
                continue

            imported_name = f"{base}.{alias.name}" if base else alias.name
            references.append(ImportReference(imported_name, node.lineno))

    return tuple(references)


def _imports_for_file(path: Path) -> tuple[ImportReference, ...]:
    module, is_package = _module_identity(path)
    return _resolved_imports(
        path.read_text(encoding="utf-8"),
        current_module=module,
        is_package=is_package,
    )


def _matches_prefix(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


def _violations(
    paths: tuple[Path, ...],
    forbidden_prefixes: tuple[str, ...],
) -> tuple[str, ...]:
    violations: set[str] = set()

    for path in paths:
        for reference in _imports_for_file(path):
            if any(
                _matches_prefix(reference.module, prefix)
                for prefix in forbidden_prefixes
            ):
                relative = path.relative_to(PROJECT_ROOT)
                violations.add(
                    f"{relative}:{reference.line} imports " f"{reference.module}"
                )

    return tuple(sorted(violations))


def _python_files(*directories: str) -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for directory in directories
            for path in (PROJECT_ROOT / directory).rglob("*.py")
        )
    )


def test_deterministic_core_does_not_import_outward() -> None:
    violations = _violations(
        _python_files(*CORE_DIRECTORIES),
        FORBIDDEN_CORE_PREFIXES,
    )

    assert violations == (), "\n".join(violations)


def test_application_does_not_import_ui_or_external_adapters() -> None:
    violations = _violations(
        _python_files("volcanoes/application"),
        FORBIDDEN_APPLICATION_PREFIXES,
    )

    assert violations == (), "\n".join(violations)


def test_no_volcanoes_module_imports_adapters() -> None:
    violations = _violations(
        _python_files("volcanoes"),
        ("adapters", "volcanoes.adapters"),
    )

    assert violations == (), "\n".join(violations)


def test_broker_portfolio_adapter_uses_only_approved_boundaries() -> None:
    adapter_path = PROJECT_ROOT / "adapters/broker_portfolio_view.py"
    allowed_project_prefixes = (
        "broker.base",
        "volcanoes.risk.portfolio_view",
    )
    project_roots = (
        "adapters",
        "broker",
        "engine",
        "scanner_engine",
        "trading",
        "volcanoes",
    )
    violations = {
        reference.module
        for reference in _imports_for_file(adapter_path)
        if any(_matches_prefix(reference.module, root) for root in project_roots)
        and not any(
            _matches_prefix(reference.module, allowed)
            for allowed in allowed_project_prefixes
        )
    }

    assert violations == set()


def test_paper_order_preview_adapter_stays_ui_and_submission_independent() -> None:
    adapter_path = PROJECT_ROOT / "adapters/paper_order_preview.py"
    allowed_project_prefixes = (
        "adapters.broker_portfolio_view",
        "adapters.paper_order_composition",
        "broker.base",
        "trading.risk_manager",
        "volcanoes",
    )
    project_roots = (
        "adapters",
        "broker",
        "database",
        "engine",
        "persistence",
        "scanner_engine",
        "streamlit",
        "trading",
        "volcanoes",
    )
    violations = {
        reference.module
        for reference in _imports_for_file(adapter_path)
        if any(_matches_prefix(reference.module, root) for root in project_roots)
        and not any(
            _matches_prefix(reference.module, allowed)
            for allowed in allowed_project_prefixes
        )
    }

    assert violations == set()


def test_preview_trade_has_no_infrastructure_dependencies() -> None:
    preview_path = PROJECT_ROOT / "volcanoes/application/services/preview_trade.py"
    violations = _violations(
        (preview_path,),
        FORBIDDEN_PREVIEW_PREFIXES,
    )

    assert violations == (), "\n".join(violations)


def test_submit_trade_has_no_ui_or_infrastructure_dependencies() -> None:
    submit_path = PROJECT_ROOT / "volcanoes/application/services/submit_trade.py"
    violations = _violations(
        (submit_path,),
        FORBIDDEN_SUBMIT_PREFIXES,
    )

    assert violations == (), "\n".join(violations)


def test_operational_events_have_no_ui_broker_or_adapter_dependencies() -> None:
    violations = _violations(
        _python_files("volcanoes/events"),
        (
            "streamlit",
            "broker",
            "adapters",
            "volcanoes.adapters",
            "volcanoes.execution.broker",
            "volcanoes.execution.paper_broker",
        ),
    )

    assert violations == (), "\n".join(violations)


def test_operational_metrics_contracts_have_no_trading_or_infrastructure_imports() -> (
    None
):
    metrics_path = PROJECT_ROOT / "volcanoes/application/operations/metrics.py"
    violations = _violations(
        (metrics_path,),
        (
            "streamlit",
            "broker",
            "adapters",
            "scanner_engine",
            "engine",
            "persistence",
            "database",
            "volcanoes.execution",
            "volcanoes.risk",
            "volcanoes.sizing",
            "volcanoes.database",
        ),
    )

    assert violations == (), "\n".join(violations)


def test_execution_supervisor_has_no_outward_or_trading_logic_dependencies() -> None:
    violations = _violations(
        _python_files("volcanoes/application/supervisor"),
        FORBIDDEN_SUPERVISOR_PREFIXES,
    )

    assert violations == (), "\n".join(violations)


def test_scanner_signal_production_has_no_execution_dependencies() -> None:
    violations = _violations(
        _python_files("scanner_engine"),
        (
            "adapters",
            "broker",
            "trading",
            "volcanoes.application",
            "volcanoes.execution",
            "volcanoes.risk",
            "volcanoes.sizing",
        ),
    )

    assert violations == (), "\n".join(violations)


def test_supervised_scanner_imports_only_the_application_execution_boundary() -> None:
    path = PROJECT_ROOT / "engine/supervised_brain.py"
    allowed_project_prefixes = (
        "audit.trade_log",
        "engine.cycle_report",
        "scanner_engine.automated_scanner",
        "strategies.trend_momentum",
        "volcanoes.application.operations",
        "volcanoes.application.supervisor",
    )
    project_roots = (
        "adapters",
        "audit",
        "broker",
        "engine",
        "scanner_engine",
        "strategies",
        "trading",
        "volcanoes",
    )
    violations = {
        reference.module
        for reference in _imports_for_file(path)
        if any(_matches_prefix(reference.module, root) for root in project_roots)
        and not any(
            _matches_prefix(reference.module, allowed)
            for allowed in allowed_project_prefixes
        )
    }

    assert violations == set()


def test_relative_broker_import_resolves_inside_volcanoes() -> None:
    references = _resolved_imports(
        "from .broker import Broker",
        current_module="volcanoes.execution.execution_pipeline",
    )
    modules = {reference.module for reference in references}

    assert "volcanoes.execution.broker" in modules
    assert not any(_matches_prefix(module, "broker") for module in modules)


@pytest.mark.parametrize(
    ("source", "expected_violation"),
    [
        ("from broker.base import PaperBroker", True),
        ("import trading.execution", True),
        ("from volcanoes.execution.broker import Broker", False),
        ("from volcanoes.execution import TradePlanner", False),
    ],
)
def test_prefix_matching_avoids_similarly_named_modules(
    source: str,
    expected_violation: bool,
) -> None:
    references = _resolved_imports(
        source,
        current_module="volcanoes.execution.example",
    )
    has_violation = any(
        _matches_prefix(reference.module, prefix)
        for reference in references
        for prefix in FORBIDDEN_CORE_PREFIXES
    )

    assert has_violation is expected_violation
