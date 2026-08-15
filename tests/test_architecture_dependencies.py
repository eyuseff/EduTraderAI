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

FORBIDDEN_QUALIFICATION_PREFIXES = (
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
    "requests",
    "http",
    "urllib",
    "socket",
    "subprocess",
)

FORBIDDEN_PAPER_EXECUTION_PREFIXES = (
    "adapters",
    "broker",
    "scanner_engine",
    "engine",
    "database",
    "persistence",
    "volcanoes.database",
    "volcanoes.persistence",
    "volcanoes.application.qualification.integration",
    "volcanoes.application.supervisor",
    "volcanoes.application.operations",
    "volcanoes.events",
    "logging",
    "requests",
    "aiohttp",
    "urllib",
    "http",
    "socket",
    "alpaca",
    "alpaca-py",
)

FORBIDDEN_PAPER_ELIGIBILITY_PREFIXES = (
    "adapters",
    "broker",
    "scanner_engine",
    "engine",
    "database",
    "persistence",
    "volcanoes.database",
    "volcanoes.persistence",
    "volcanoes.application.qualification.integration",
    "volcanoes.application.supervisor",
    "volcanoes.application.operations",
    "volcanoes.events",
    "logging",
    "requests",
    "aiohttp",
    "urllib",
    "http",
    "socket",
    "alpaca",
)

FORBIDDEN_PAPER_LIFECYCLE_PREFIXES = FORBIDDEN_PAPER_EXECUTION_PREFIXES + (
    "volcanoes.application.execution.eligibility",
    "volcanoes.application.qualification",
)

FORBIDDEN_PAPER_DRY_RUN_PREFIXES = FORBIDDEN_PAPER_EXECUTION_PREFIXES + (
    "volcanoes.application.qualification",
    "volcanoes.application.qualification.integration",
    "volcanoes.application.qualification.integration.readiness",
    "volcanoes.application.supervisor",
    "volcanoes.events",
)

ALLOWED_EXECUTION_PERSISTENCE_PREFIXES = (
    "volcanoes.application.execution._canonical",
    "volcanoes.application.execution.contracts",
    "volcanoes.application.execution.enums",
    "volcanoes.application.execution.errors",
    "volcanoes.application.execution.fingerprints",
    "volcanoes.application.execution.identities",
    "volcanoes.application.execution.lifecycle",
    "volcanoes.application.execution.persistence",
)

FORBIDDEN_EXECUTION_PERSISTENCE_PREFIXES = (
    "adapters",
    "broker",
    "scanner_engine",
    "engine",
    "trading",
    "database",
    "persistence",
    "volcanoes.database",
    "volcanoes.persistence",
    "volcanoes.application.supervisor",
    "volcanoes.application.operations",
    "volcanoes.application.platform",
    "volcanoes.application.qualification.integration",
    "volcanoes.events",
    "sqlite3",
    "psycopg",
    "sqlalchemy",
    "redis",
    "requests",
    "aiohttp",
    "urllib",
    "http",
    "socket",
    "subprocess",
    "os",
    "pathlib",
    "random",
    "uuid",
    "threading",
    "multiprocessing",
    "logging",
)

FORBIDDEN_TRANSACTIONAL_INTAKE_PREFIXES = FORBIDDEN_EXECUTION_PERSISTENCE_PREFIXES + (
    "volcanoes.infrastructure",
    "volcanoes.execution",
)

FORBIDDEN_CERTIFICATION_PREFIXES = FORBIDDEN_EXECUTION_PERSISTENCE_PREFIXES + (
    "volcanoes.infrastructure",
    "volcanoes.execution",
    "volcanoes.application.execution.persistence",
    "volcanoes.application.execution.intake",
    "volcanoes.application.execution.pipeline",
    "volcanoes.application.execution.runtime",
)

FORBIDDEN_CONTROLLED_SUBMISSION_PREFIXES = FORBIDDEN_EXECUTION_PERSISTENCE_PREFIXES + (
    "volcanoes.infrastructure",
    "volcanoes.execution",
    "volcanoes.application.execution.intake",
    "volcanoes.application.execution.pipeline",
    "volcanoes.application.execution.runtime",
    "volcanoes.application.services",
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
                    f"{relative}:{reference.line} imports {reference.module}"
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


def test_qualification_package_has_no_external_or_infrastructure_dependencies() -> None:
    violations = _violations(
        _python_files("volcanoes/application/qualification"),
        FORBIDDEN_QUALIFICATION_PREFIXES,
    )

    assert violations == (), "\n".join(violations)


def test_qualification_service_depends_only_on_domain_and_ports() -> None:
    path = PROJECT_ROOT / "volcanoes/application/qualification/service.py"
    allowed_project_prefixes = (
        "volcanoes.application.qualification.contracts",
        "volcanoes.application.qualification.errors",
        "volcanoes.application.qualification.ports",
        "volcanoes.application.qualification.state_machine",
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
        for reference in _imports_for_file(path)
        if any(_matches_prefix(reference.module, root) for root in project_roots)
        and not any(
            _matches_prefix(reference.module, allowed)
            for allowed in allowed_project_prefixes
        )
    }

    assert violations == set()


def test_qualification_state_machine_does_not_import_service_layer() -> None:
    path = PROJECT_ROOT / "volcanoes/application/qualification/state_machine.py"
    violations = _violations(
        (path,),
        ("volcanoes.application.qualification.service",),
    )

    assert violations == (), "\n".join(violations)


def test_qualification_package_has_no_runtime_side_effect_tokens() -> None:
    prohibited_tokens = (
        "os.environ",
        "TradingClient",
        "WebSocket",
        "simulated_broker",
        "BrokerAdapter",
        "subprocess",
    )
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/qualification"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_qualification_scenario_harness_has_no_external_dependencies() -> None:
    scenario_paths = (
        PROJECT_ROOT / "volcanoes/application/qualification/scenario_models.py",
        PROJECT_ROOT / "volcanoes/application/qualification/scenario_catalog.py",
        PROJECT_ROOT / "volcanoes/application/qualification/scenario_validation.py",
        PROJECT_ROOT / "volcanoes/application/qualification/scenario_harness.py",
    )
    violations = _violations(
        scenario_paths,
        (
            "streamlit",
            "adapters",
            "volcanoes.adapters",
            "broker",
            "scanner_engine",
            "engine",
            "trading",
            "requests",
            "http",
            "urllib",
            "socket",
            "subprocess",
            "os",
            "random",
            "uuid",
            "pathlib",
        ),
    )

    assert violations == (), "\n".join(violations)


def test_qualification_scenario_modules_do_not_touch_runtime_state_or_network() -> None:
    prohibited_tokens = (
        "state/simulated_broker.json",
        "simulated_broker",
        "TradingClient",
        "Alpaca",
        "WebSocket",
        "import requests",
        "from requests",
        "socket",
        "subprocess",
        "os.environ",
        "open(",
        "Path(",
        "uuid4",
        "random",
        "datetime.now",
        "BrokerAdapter",
    )
    scenario_files = (
        PROJECT_ROOT / "volcanoes/application/qualification/scenario_models.py",
        PROJECT_ROOT / "volcanoes/application/qualification/scenario_catalog.py",
        PROJECT_ROOT / "volcanoes/application/qualification/scenario_validation.py",
        PROJECT_ROOT / "volcanoes/application/qualification/scenario_harness.py",
    )
    offenders: list[str] = []
    for path in scenario_files:
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_state_machine_and_service_do_not_import_scenario_harness() -> None:
    violations = _violations(
        (
            PROJECT_ROOT / "volcanoes/application/qualification/state_machine.py",
            PROJECT_ROOT / "volcanoes/application/qualification/service.py",
        ),
        (
            "volcanoes.application.qualification.scenario_harness",
            "volcanoes.application.qualification.scenario_catalog",
            "volcanoes.application.qualification.scenario_models",
        ),
    )

    assert violations == (), "\n".join(violations)


def test_evidence_adapter_has_no_outward_or_infrastructure_dependencies() -> None:
    path = PROJECT_ROOT / "volcanoes/application/qualification/evidence.py"
    violations = _violations(
        (path,),
        (
            "streamlit",
            "adapters",
            "volcanoes.adapters",
            "broker",
            "scanner_engine",
            "engine",
            "trading",
            "requests",
            "http",
            "urllib",
            "socket",
            "subprocess",
            "os",
            "pathlib",
            "volcanoes.events",
        ),
    )

    assert violations == (), "\n".join(violations)


def test_evidence_adapter_has_no_runtime_effect_tokens() -> None:
    prohibited_tokens = (
        "state/simulated_broker.json",
        "simulated_broker",
        "TradingClient",
        "Alpaca",
        "WebSocket",
        "import requests",
        "from requests",
        "socket",
        "subprocess",
        "os.environ",
        "getenv",
        "open(",
        "Path(",
        "write_text",
        "write_bytes",
        "uuid4",
        "random",
        "datetime.now",
        "time.time",
        "BrokerAdapter",
        "EventPublisher",
        "Kafka",
        "Rabbit",
        "Redis",
    )
    path = PROJECT_ROOT / "volcanoes/application/qualification/evidence.py"
    source = path.read_text(encoding="utf-8")
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)} contains {token}"
        for token in prohibited_tokens
        if token in source
    ]

    assert offenders == []


def test_service_does_not_implement_canonical_evidence_serialization() -> None:
    path = PROJECT_ROOT / "volcanoes/application/qualification/service.py"
    source = path.read_text(encoding="utf-8")

    assert "serialize_qualification_evidence" not in source
    assert "QualificationEvidenceRecord(" not in source
    assert "compute_evidence_digest" not in source


def test_state_machine_and_scenario_models_do_not_import_evidence_adapter() -> None:
    violations = _violations(
        (
            PROJECT_ROOT / "volcanoes/application/qualification/state_machine.py",
            PROJECT_ROOT / "volcanoes/application/qualification/scenario_models.py",
        ),
        ("volcanoes.application.qualification.evidence",),
    )

    assert violations == (), "\n".join(violations)


def test_qualification_integration_has_no_runtime_or_infrastructure_imports() -> None:
    violations = _violations(
        _python_files("volcanoes/application/qualification/integration"),
        (
            "streamlit",
            "adapters",
            "volcanoes.adapters",
            "broker",
            "scanner_engine",
            "engine",
            "trading",
            "requests",
            "http",
            "urllib",
            "socket",
            "subprocess",
            "os",
            "pathlib",
            "random",
            "uuid",
            "volcanoes.events",
            "volcanoes.database",
            "volcanoes.persistence",
        ),
    )

    assert violations == (), "\n".join(violations)


def test_qualification_integration_service_dependency_is_contract_or_facade_only() -> (
    None
):
    violations = _violations(
        tuple(
            path
            for path in _python_files("volcanoes/application/qualification/integration")
            if path.name not in {"facade.py", "translation.py"}
        ),
        ("volcanoes.application.qualification.service",),
    )

    assert violations == (), "\n".join(violations)


def test_qualification_facade_does_not_construct_service_or_call_state_machine() -> (
    None
):
    prohibited_tokens = (
        "PaperQualificationService(",
        "transition(",
        "apply_transition",
        "diagnostic_rejection",
    )
    offenders: list[str] = []
    path = PROJECT_ROOT / "volcanoes/application/qualification/integration/facade.py"
    source = path.read_text(encoding="utf-8")
    offenders.extend(
        f"{path.relative_to(PROJECT_ROOT)} contains {token}"
        for token in prohibited_tokens
        if token in source
    )
    violations = _violations(
        (path,),
        ("volcanoes.application.qualification.state_machine",),
    )
    offenders.extend(violations)

    assert offenders == []


def test_qualification_shadow_does_not_construct_facade_service_or_call_state_machine() -> (
    None
):
    prohibited_tokens = (
        "PaperQualificationFacade(",
        "PaperQualificationService(",
        "transition(",
        "apply_transition",
        "diagnostic_rejection",
        "RuntimeActionRequest(",
    )
    path = PROJECT_ROOT / "volcanoes/application/qualification/integration/shadow.py"
    source = path.read_text(encoding="utf-8")
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)} contains {token}"
        for token in prohibited_tokens
        if token in source
    ]
    offenders.extend(
        _violations(
            (path,),
            (
                "volcanoes.application.qualification.state_machine",
                "volcanoes.application.qualification.evidence",
                "volcanoes.application.qualification.ports",
                "volcanoes.application.qualification.service",
                "volcanoes.events",
                "volcanoes.application.operations",
            ),
        )
    )

    assert offenders == []


def test_qualification_runtime_boundary_imports_only_shadow_boundary_dependencies() -> (
    None
):
    path = PROJECT_ROOT / "volcanoes/application/qualification/integration/boundary.py"
    violations = _violations(
        (path,),
        (
            "streamlit",
            "adapters",
            "volcanoes.adapters",
            "broker",
            "scanner_engine",
            "engine",
            "trading",
            "requests",
            "http",
            "urllib",
            "socket",
            "subprocess",
            "os",
            "pathlib",
            "random",
            "uuid",
            "volcanoes.application.qualification.service",
            "volcanoes.application.qualification.state_machine",
            "volcanoes.application.qualification.evidence",
            "volcanoes.application.qualification.ports",
            "volcanoes.events",
            "volcanoes.application.operations",
            "volcanoes.application.platform",
        ),
    )

    assert violations == (), "\n".join(violations)


def test_qualification_runtime_boundary_has_no_execution_hooks_or_construction() -> (
    None
):
    prohibited_tokens = (
        "PaperQualificationShadowRunner(",
        "PaperQualificationFacade(",
        "PaperQualificationService(",
        "transition(",
        "apply_transition",
        "diagnostic_rejection",
        "RuntimeActionRequest(",
        "execute(",
        "submit",
        "cancel",
        "feature_flag",
    )
    path = PROJECT_ROOT / "volcanoes/application/qualification/integration/boundary.py"
    source = path.read_text(encoding="utf-8")
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)} contains {token}"
        for token in prohibited_tokens
        if token in source
    ]

    assert offenders == []


def test_shadow_mode_is_not_wired_into_current_runtime_entry_points() -> None:
    prohibited_tokens = (
        "PaperQualificationShadowRunner",
        "PaperQualificationShadowRequest",
        "PaperQualificationShadowResult",
        "LegacyPaperDecision",
        "qualification.integration.shadow",
    )
    runtime_paths = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "adapters/paper_order_preview.py",
        PROJECT_ROOT / "adapters/paper_order_submission.py",
        PROJECT_ROOT / "adapters/scanner_execution.py",
        PROJECT_ROOT / "engine/supervised_brain.py",
        PROJECT_ROOT / "engine/brain.py",
    )
    offenders: list[str] = []
    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_shadow_validation_harness_imports_only_boundary_contracts() -> None:
    path = (
        PROJECT_ROOT / "volcanoes/application/qualification/integration/validation.py"
    )
    allowed_project_prefixes = (
        "volcanoes.application.qualification.integration.boundary",
        "volcanoes.application.qualification.integration.contracts",
        "volcanoes.application.qualification.integration.shadow",
    )
    forbidden_prefixes = (
        "streamlit",
        "app",
        "adapters",
        "volcanoes.adapters",
        "broker",
        "scanner_engine",
        "engine",
        "trading",
        "requests",
        "http",
        "urllib",
        "socket",
        "subprocess",
        "os",
        "pathlib",
        "random",
        "uuid",
        "datetime",
        "time",
        "database",
        "persistence",
        "volcanoes.database",
        "volcanoes.persistence",
        "volcanoes.events",
        "volcanoes.application.operations",
        "volcanoes.application.platform",
        "volcanoes.application.supervisor",
        "volcanoes.application.qualification.runtime_observation",
        "volcanoes.application.qualification.integration.runtime_observation",
        "volcanoes.application.qualification.integration.facade",
        "volcanoes.application.qualification.integration.evidence",
        "volcanoes.application.qualification.integration.service",
        "volcanoes.application.qualification.integration.state_machine",
        "volcanoes.application.qualification.integration.ports",
        "volcanoes.application.qualification.integration.shadow.PaperQualificationShadowRunner",
        "volcanoes.application.qualification.facade",
        "volcanoes.application.qualification.service",
        "volcanoes.application.qualification.state_machine",
        "volcanoes.application.qualification.evidence",
        "volcanoes.application.qualification.ports",
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
        for reference in _imports_for_file(path)
        if any(
            _matches_prefix(reference.module, prefix) for prefix in forbidden_prefixes
        )
        or (
            any(_matches_prefix(reference.module, root) for root in project_roots)
            and not any(
                _matches_prefix(reference.module, allowed)
                for allowed in allowed_project_prefixes
            )
        )
    }

    assert violations == set()


def test_shadow_validation_harness_has_no_runtime_effect_or_authority_tokens() -> None:
    path = (
        PROJECT_ROOT / "volcanoes/application/qualification/integration/validation.py"
    )
    prohibited_tokens = (
        "evaluate_shadow(",
        "PaperQualificationShadowRunner(",
        "PaperQualificationFacade(",
        "PaperQualificationService(",
        "transition(",
        "apply_transition",
        "RuntimeActionRequest(",
        "TradingClient",
        "Alpaca",
        "BrokerAdapter",
        "simulated_broker",
        "scanner",
        "supervisor",
        "streamlit",
        "requests",
        "http",
        "https",
        "socket",
        "WebSocket",
        "subprocess",
        "os.environ",
        "getenv",
        "open(",
        "Path(",
        "read_text",
        "write_text",
        "write_bytes",
        "uuid4",
        "random",
        "datetime.now",
        "time.time",
        "EventPublisher",
        "metrics",
        "logging",
        "print(",
        "execute(",
        "submit",
        "cancel",
        "reconcile",
        "database",
        "sqlite",
        "postgres",
        "redis",
        "Kafka",
        "Rabbit",
        "API_KEY",
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "authorization",
        "cookie",
        "LIVE",
        "READY",
    )
    source = path.read_text(encoding="utf-8")
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)} contains {token}"
        for token in prohibited_tokens
        if token in source
    ]

    assert offenders == []


def test_no_reverse_dependency_into_shadow_validation_harness() -> None:
    paths = (
        PROJECT_ROOT / "volcanoes/application/qualification/service.py",
        PROJECT_ROOT / "volcanoes/application/qualification/state_machine.py",
        PROJECT_ROOT / "volcanoes/application/qualification/evidence.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/boundary.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/shadow.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/facade.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/translation.py",
        PROJECT_ROOT
        / "volcanoes/application/qualification/integration/runtime_observation.py",
    )
    violations = _violations(
        paths,
        ("volcanoes.application.qualification.integration.validation",),
    )

    assert violations == (), "\n".join(violations)


def test_shadow_readiness_imports_only_validation_contracts() -> None:
    path = PROJECT_ROOT / "volcanoes/application/qualification/integration/readiness.py"
    allowed_project_prefixes = (
        "volcanoes.application.qualification.integration.validation",
    )
    forbidden_prefixes = (
        "streamlit",
        "app",
        "adapters",
        "volcanoes.adapters",
        "broker",
        "scanner_engine",
        "engine",
        "trading",
        "requests",
        "http",
        "urllib",
        "socket",
        "subprocess",
        "os",
        "pathlib",
        "random",
        "uuid",
        "datetime",
        "time",
        "database",
        "persistence",
        "volcanoes.database",
        "volcanoes.persistence",
        "volcanoes.events",
        "volcanoes.application.operations",
        "volcanoes.application.platform",
        "volcanoes.application.supervisor",
        "volcanoes.application.qualification.integration.runtime_observation",
        "volcanoes.application.qualification.integration.boundary",
        "volcanoes.application.qualification.integration.shadow",
        "volcanoes.application.qualification.integration.facade",
        "volcanoes.application.qualification.integration.service",
        "volcanoes.application.qualification.integration.state_machine",
        "volcanoes.application.qualification.integration.evidence",
        "volcanoes.application.qualification.integration.ports",
        "volcanoes.application.qualification.facade",
        "volcanoes.application.qualification.service",
        "volcanoes.application.qualification.state_machine",
        "volcanoes.application.qualification.evidence",
        "volcanoes.application.qualification.ports",
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
        for reference in _imports_for_file(path)
        if any(
            _matches_prefix(reference.module, prefix) for prefix in forbidden_prefixes
        )
        or (
            any(_matches_prefix(reference.module, root) for root in project_roots)
            and not any(
                _matches_prefix(reference.module, allowed)
                for allowed in allowed_project_prefixes
            )
        )
    }

    assert violations == set()


def test_shadow_readiness_has_no_runtime_effect_or_authority_tokens() -> None:
    path = PROJECT_ROOT / "volcanoes/application/qualification/integration/readiness.py"
    prohibited_tokens = (
        ".record(",
        ".summarize(",
        "evaluate_shadow(",
        "PaperQualificationShadowRunner(",
        "PaperQualificationFacade(",
        "PaperQualificationService(",
        "transition(",
        "apply_transition",
        "RuntimeActionRequest(",
        "TradingClient",
        "Alpaca",
        "BrokerAdapter",
        "simulated_broker",
        "scanner",
        "supervisor",
        "streamlit",
        "requests",
        "http",
        "https",
        "socket",
        "WebSocket",
        "subprocess",
        "os.environ",
        "getenv",
        "open(",
        "Path(",
        "read_text",
        "write_text",
        "write_bytes",
        "uuid4",
        "random",
        "datetime.now",
        "time.time",
        "EventPublisher",
        "metrics",
        "logging",
        "print(",
        "execute(",
        "submit",
        "cancel",
        "reconcile",
        "database",
        "sqlite",
        "postgres",
        "redis",
        "Kafka",
        "Rabbit",
        "API_KEY",
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "authorization",
        "cookie",
        "EXECUTION_AUTHORIZED",
        "PRODUCTION_READY",
    )
    source = path.read_text(encoding="utf-8")
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)} contains {token}"
        for token in prohibited_tokens
        if token in source
    ]

    assert offenders == []


def test_no_reverse_dependency_into_shadow_readiness() -> None:
    paths = (
        PROJECT_ROOT / "volcanoes/application/qualification/service.py",
        PROJECT_ROOT / "volcanoes/application/qualification/state_machine.py",
        PROJECT_ROOT / "volcanoes/application/qualification/evidence.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/boundary.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/shadow.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/facade.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/translation.py",
        PROJECT_ROOT
        / "volcanoes/application/qualification/integration/runtime_observation.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/validation.py",
    )
    violations = _violations(
        paths,
        ("volcanoes.application.qualification.integration.readiness",),
    )

    assert violations == (), "\n".join(violations)


def test_shadow_readiness_is_not_wired_into_runtime_entry_points() -> None:
    runtime_paths = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "adapters/paper_order_preview.py",
        PROJECT_ROOT / "adapters/paper_order_submission.py",
        PROJECT_ROOT / "adapters/scanner_execution.py",
        PROJECT_ROOT / "adapters/paper_broker_execution.py",
        PROJECT_ROOT / "broker/simulated.py",
        PROJECT_ROOT / "engine/supervised_brain.py",
        PROJECT_ROOT / "engine/brain.py",
        PROJECT_ROOT / "scanner_engine/__init__.py",
    )
    prohibited_tokens = (
        "ShadowReadinessAssessmentService",
        "ShadowReadinessPolicy",
        "ShadowReadinessDecision",
        "qualification.integration.readiness",
    )
    offenders: list[str] = []
    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_controlled_shadow_runtime_observation_has_one_call_site() -> None:
    runtime_paths = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "adapters/paper_order_preview.py",
        PROJECT_ROOT / "adapters/paper_order_submission.py",
        PROJECT_ROOT / "adapters/scanner_execution.py",
        PROJECT_ROOT / "adapters/paper_broker_execution.py",
        PROJECT_ROOT / "broker/simulated.py",
        PROJECT_ROOT / "engine/supervised_brain.py",
        PROJECT_ROOT / "engine/brain.py",
        PROJECT_ROOT / "scanner_engine/__init__.py",
    )
    call_sites: list[str] = []

    for path in runtime_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if isinstance(function, ast.Name):
                called_name = function.id
            elif isinstance(function, ast.Attribute):
                called_name = function.attr
            else:
                called_name = ""
            if called_name == "observe_paper_preview_decision":
                call_sites.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")

    assert len(call_sites) == 1
    assert call_sites[0].startswith("adapters/paper_order_preview.py:")


def test_controlled_shadow_runtime_wiring_is_preview_only_and_disabled_by_default() -> (
    None
):
    runtime_paths = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "adapters/paper_order_submission.py",
        PROJECT_ROOT / "adapters/scanner_execution.py",
        PROJECT_ROOT / "adapters/paper_broker_execution.py",
        PROJECT_ROOT / "broker/simulated.py",
        PROJECT_ROOT / "engine/supervised_brain.py",
        PROJECT_ROOT / "engine/brain.py",
    )
    prohibited_tokens = (
        "PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY",
        "observe_paper_preview_decision",
        "PaperPreviewObservationFacts",
    )
    offenders: list[str] = []
    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    preview_source = (PROJECT_ROOT / "adapters/paper_order_preview.py").read_text(
        encoding="utf-8"
    )

    assert offenders == []
    assert "PaperQualificationShadowGate.DISABLED" in preview_source


def test_controlled_shadow_runtime_adapter_does_not_construct_the_stack() -> None:
    path = (
        PROJECT_ROOT
        / "volcanoes/application/qualification/integration/runtime_observation.py"
    )
    prohibited_tokens = (
        "PaperQualificationShadowRunner(",
        "PaperQualificationFacade(",
        "PaperQualificationService(",
        "transition(",
        "apply_transition",
        "diagnostic_rejection",
        "RuntimeActionRequest(",
        "submit",
        "cancel",
        "feature_flag",
        "os.environ",
        "getenv",
        "EventPublisher",
    )
    source = path.read_text(encoding="utf-8")
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)} contains {token}"
        for token in prohibited_tokens
        if token in source
    ]

    assert offenders == []


def test_runtime_boundary_is_not_constructed_in_current_runtime_entry_points() -> None:
    prohibited_tokens = (
        "QualificationRuntimeBoundaryRequest",
        "QualificationRuntimeBoundaryResult",
        "QualificationRuntimeBoundaryMode",
        "qualification.integration.boundary",
    )
    runtime_paths = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "adapters/paper_order_preview.py",
        PROJECT_ROOT / "adapters/paper_order_submission.py",
        PROJECT_ROOT / "adapters/scanner_execution.py",
        PROJECT_ROOT / "adapters/paper_broker_execution.py",
        PROJECT_ROOT / "broker/simulated.py",
        PROJECT_ROOT / "engine/supervised_brain.py",
        PROJECT_ROOT / "engine/brain.py",
    )
    offenders: list[str] = []
    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_no_reverse_dependency_from_facade_or_core_into_shadow_module() -> None:
    paths = (
        PROJECT_ROOT / "volcanoes/application/qualification/facade.py",
        PROJECT_ROOT / "volcanoes/application/qualification/service.py",
        PROJECT_ROOT / "volcanoes/application/qualification/state_machine.py",
        PROJECT_ROOT / "volcanoes/application/qualification/evidence.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/facade.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/translation.py",
    )
    existing_paths = tuple(path for path in paths if path.exists())

    violations = _violations(
        existing_paths,
        ("volcanoes.application.qualification.integration.shadow",),
    )

    assert violations == (), "\n".join(violations)


def test_no_reverse_dependency_from_shadow_facade_or_core_into_boundary_module() -> (
    None
):
    paths = (
        PROJECT_ROOT / "volcanoes/application/qualification/service.py",
        PROJECT_ROOT / "volcanoes/application/qualification/state_machine.py",
        PROJECT_ROOT / "volcanoes/application/qualification/evidence.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/shadow.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/facade.py",
        PROJECT_ROOT / "volcanoes/application/qualification/integration/translation.py",
    )

    violations = _violations(
        paths,
        ("volcanoes.application.qualification.integration.boundary",),
    )

    assert violations == (), "\n".join(violations)


def test_qualification_integration_has_no_effect_or_runtime_tokens() -> None:
    prohibited_tokens = (
        "state/simulated_broker.json",
        "simulated_broker",
        "TradingClient",
        "Alpaca",
        "WebSocket",
        "import requests",
        "from requests",
        "socket",
        "subprocess",
        "os.environ",
        "getenv",
        "open(",
        "Path(",
        "read_text",
        "write_text",
        "write_bytes",
        "uuid4",
        "random",
        "datetime.now",
        "time.time",
        "BrokerAdapter",
        "EventPublisher",
        "Kafka",
        "Rabbit",
        "Redis",
    )
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/qualification/integration"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_qualification_core_does_not_import_integration_package() -> None:
    core_files = tuple(
        path
        for path in _python_files("volcanoes/application/qualification")
        if "integration" not in path.relative_to(PROJECT_ROOT).parts
    )
    violations = _violations(
        core_files,
        ("volcanoes.application.qualification.integration",),
    )

    assert violations == (), "\n".join(violations)


def test_scenario_harness_invokes_application_service_not_transition_engine() -> None:
    path = PROJECT_ROOT / "volcanoes/application/qualification/scenario_harness.py"
    source = path.read_text(encoding="utf-8")
    imports = {reference.module for reference in _imports_for_file(path)}

    assert "volcanoes.application.qualification.service" in imports
    assert (
        "volcanoes.application.qualification.state_machine.apply_transition"
        not in imports
    )
    assert "apply_transition" not in source


def test_scenario_specifications_do_not_contain_callables() -> None:
    source = (
        PROJECT_ROOT / "volcanoes/application/qualification/scenario_catalog.py"
    ).read_text(encoding="utf-8")

    assert "lambda" not in source
    assert "Callable" not in source


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


def test_qualification_does_not_import_paper_execution_contracts() -> None:
    violations = _violations(
        _python_files("volcanoes/application/qualification"),
        ("volcanoes.application.execution",),
    )

    assert violations == (), "\n".join(violations)


def test_readiness_does_not_import_paper_execution_contracts() -> None:
    readiness_path = (
        PROJECT_ROOT / "volcanoes/application/qualification/integration/readiness.py"
    )
    violations = _violations(
        (readiness_path,),
        ("volcanoes.application.execution",),
    )

    assert violations == (), "\n".join(violations)


def test_paper_execution_contracts_have_no_outward_dependencies() -> None:
    violations = _violations(
        _python_files("volcanoes/application/execution"),
        FORBIDDEN_PAPER_EXECUTION_PREFIXES,
    )

    assert violations == (), "\n".join(violations)


def test_execution_persistence_imports_only_contract_dependencies() -> None:
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
    violations: set[str] = set()
    for path in _python_files("volcanoes/application/execution/persistence"):
        for reference in _imports_for_file(path):
            if any(
                _matches_prefix(reference.module, prefix)
                for prefix in FORBIDDEN_EXECUTION_PERSISTENCE_PREFIXES
            ):
                violations.add(
                    f"{path.relative_to(PROJECT_ROOT)}:{reference.line} "
                    f"imports {reference.module}"
                )
            if any(_matches_prefix(reference.module, root) for root in project_roots):
                if not any(
                    _matches_prefix(reference.module, allowed)
                    for allowed in ALLOWED_EXECUTION_PERSISTENCE_PREFIXES
                ):
                    violations.add(
                        f"{path.relative_to(PROJECT_ROOT)}:{reference.line} "
                        f"imports {reference.module}"
                    )

    assert tuple(sorted(violations)) == ()


def test_execution_persistence_has_no_runtime_storage_or_effect_tokens() -> None:
    prohibited_tokens = (
        "state/simulated_broker.json",
        "simulated_broker",
        "TradingClient",
        "Alpaca",
        "WebSocket",
        "submit_order",
        "replace_order",
        "cancel_order",
        "call_broker",
        "BrokerAdapter",
        "PaperBrokerPort",
        "EventPublisher",
        "OperationalMetrics",
        "sqlite3",
        "psycopg",
        "SQLAlchemy",
        "Redis",
        "import requests",
        "from requests",
        "import http",
        "from http",
        "socket",
        "subprocess",
        "os.environ",
        "os.getenv",
        "getenv(",
        "Path(",
        "open(",
        "read_text",
        "write_text",
        "write_bytes",
        "datetime.now",
        "time.time",
        "random",
        "uuid4",
        "threading",
        "multiprocessing",
        "logging",
        "metrics",
        "create_schema",
        "execute_sql",
        "migrate",
        "fsync",
    )
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution/persistence"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_execution_persistence_contract_files_define_no_concrete_adapters_or_schemas() -> (
    None
):
    prohibited_class_fragments = (
        "Adapter",
        "InMemory",
        "SQLite",
        "Postgres",
        "Redis",
        "Schema",
        "Migration",
        "Runtime",
    )
    offenders: list[str] = []
    for path in tuple(
        path
        for path in _python_files("volcanoes/application/execution/persistence")
        if "in_memory" not in path.relative_to(PROJECT_ROOT).parts
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                fragment in node.name for fragment in prohibited_class_fragments
            ):
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)} defines {node.name}"
                )

    assert offenders == []


def test_execution_persistence_defines_no_broker_or_runtime_call_site() -> None:
    prohibited_method_names = {
        "connect",
        "create_schema",
        "migrate",
        "execute_sql",
        "flush_to_disk",
        "fsync",
        "acquire_lock",
        "publish",
        "call_broker",
        "recover_automatically",
        "retry",
        "submit",
        "dispatch",
        "cancel_order",
        "replace_order",
    }
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution/persistence"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name in prohibited_method_names
            ):
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)} defines {node.name}"
                )

    assert offenders == []


def test_execution_persistence_is_not_wired_into_runtime_entry_points() -> None:
    runtime_paths = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "adapters/paper_order_preview.py",
        PROJECT_ROOT / "adapters/paper_order_submission.py",
        PROJECT_ROOT / "adapters/scanner_execution.py",
        PROJECT_ROOT / "adapters/paper_broker_execution.py",
        PROJECT_ROOT / "broker/simulated.py",
        PROJECT_ROOT / "engine/supervised_brain.py",
        PROJECT_ROOT / "engine/brain.py",
        PROJECT_ROOT / "scanner_engine/automated_scanner.py",
    )
    prohibited_tokens = (
        "volcanoes.application.execution.persistence",
        "ExecutionUnitOfWork",
        "ExecutionPersistenceSession",
        "ExecutionAggregateRepository",
    )
    offenders: list[str] = []
    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_in_memory_persistence_implements_ports() -> None:
    from volcanoes.application.execution.persistence import (
        ExecutionAggregateRepository,
        ExecutionApprovalRepository,
        ExecutionBrokerReferenceRepository,
        ExecutionCommandRepository,
        ExecutionFailureRepository,
        ExecutionIdempotencyRepository,
        ExecutionReceiptRepository,
        ExecutionReconciliationRepository,
        ExecutionRestartDiscoveryRepository,
        ExecutionTransitionJournal,
        ExecutionUnitOfWork,
        InMemoryExecutionPersistence,
    )

    unit_of_work = InMemoryExecutionPersistence().unit_of_work()

    assert isinstance(unit_of_work, ExecutionUnitOfWork)
    assert isinstance(unit_of_work.aggregates, ExecutionAggregateRepository)
    assert isinstance(unit_of_work.commands, ExecutionCommandRepository)
    assert isinstance(unit_of_work.idempotency, ExecutionIdempotencyRepository)
    assert isinstance(unit_of_work.transitions, ExecutionTransitionJournal)
    assert isinstance(
        unit_of_work.broker_references, ExecutionBrokerReferenceRepository
    )
    assert isinstance(unit_of_work.receipts, ExecutionReceiptRepository)
    assert isinstance(unit_of_work.failures, ExecutionFailureRepository)
    assert isinstance(unit_of_work.approvals, ExecutionApprovalRepository)
    assert isinstance(unit_of_work.reconciliations, ExecutionReconciliationRepository)
    assert isinstance(
        unit_of_work.restart_discovery, ExecutionRestartDiscoveryRepository
    )


def test_in_memory_persistence_imports_no_infrastructure_or_runtime_modules() -> None:
    violations = _violations(
        _python_files("volcanoes/application/execution/persistence/in_memory"),
        (
            "adapters",
            "broker",
            "scanner_engine",
            "engine",
            "trading",
            "database",
            "volcanoes.database",
            "volcanoes.application.supervisor",
            "volcanoes.application.operations",
            "volcanoes.application.platform",
            "volcanoes.application.qualification.integration",
            "volcanoes.events",
            "sqlite3",
            "psycopg",
            "sqlalchemy",
            "redis",
            "requests",
            "aiohttp",
            "urllib",
            "http",
            "socket",
            "subprocess",
            "os",
            "pathlib",
            "time",
            "random",
            "uuid",
            "secrets",
            "threading",
            "multiprocessing",
            "logging",
        ),
    )

    assert violations == (), "\n".join(violations)


def test_in_memory_persistence_has_no_storage_effect_or_runtime_tokens() -> None:
    prohibited_tokens = (
        "state/simulated_broker.json",
        "simulated_broker",
        "TradingClient",
        "Alpaca",
        "WebSocket",
        "submit_order",
        "replace_order",
        "cancel_order",
        "call_broker",
        "BrokerAdapter",
        "EventPublisher",
        "OperationalMetrics",
        "sqlite3",
        "psycopg",
        "SQLAlchemy",
        "Redis",
        "import requests",
        "from requests",
        "import http",
        "from http",
        "socket",
        "subprocess",
        "os.environ",
        "os.getenv",
        "getenv(",
        "Path(",
        "open(",
        "read_text",
        "write_text",
        "write_bytes",
        "json.dump",
        "jsonlines",
        "datetime.now",
        "datetime.utcnow",
        "time.time",
        "uuid4",
        "random",
        "secrets",
        "threading",
        "multiprocessing",
        "logging",
        "metrics",
        "create_schema",
        "execute_sql",
        "migrate",
        "fsync",
        "LIVE",
        "PRODUCTION",
    )
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution/persistence/in_memory"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_in_memory_persistence_is_not_wired_into_runtime_entry_points() -> None:
    runtime_paths = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "adapters/paper_order_preview.py",
        PROJECT_ROOT / "adapters/paper_order_submission.py",
        PROJECT_ROOT / "adapters/scanner_execution.py",
        PROJECT_ROOT / "adapters/paper_broker_execution.py",
        PROJECT_ROOT / "broker/simulated.py",
        PROJECT_ROOT / "engine/supervised_brain.py",
        PROJECT_ROOT / "engine/brain.py",
        PROJECT_ROOT / "scanner_engine/automated_scanner.py",
    )
    offenders: list[str] = []
    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in (
                "InMemoryExecutionPersistence",
                "persistence.in_memory",
            )
            if token in source
        )

    assert offenders == []


def test_paper_execution_contracts_do_not_read_environment() -> None:
    prohibited_tokens = (
        "os.environ",
        "os.getenv",
        "getenv(",
        "environ[",
    )
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_paper_execution_contracts_have_no_live_mode_or_runtime_selection() -> None:
    package_root = PROJECT_ROOT / "volcanoes/application/execution"
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in ("LIVE", "PRODUCTION", "REAL_MONEY", "endpoint", "base_url")
            if token in source
        )

    assert offenders == []
    assert package_root.exists()


def test_paper_execution_contracts_define_no_executor_or_behavior_methods() -> None:
    prohibited_class_names = {
        "PaperExecutor",
        "ExecutionExecutor",
        "PaperExecutionExecutor",
        "PaperExecutionService",
        "PaperExecutionRuntime",
    }
    prohibited_method_names = {
        "execute",
        "submit",
        "dispatch",
        "cancel_order",
        "replace_order",
        "retry",
        "reconcile",
        "persist",
        "approve",
        "authorize",
        "connect",
        "send",
        "call_broker",
    }
    offenders: list[str] = []
    for path in tuple(
        path
        for path in _python_files("volcanoes/application/execution")
        if "dry_run" not in path.relative_to(PROJECT_ROOT).parts
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in prohibited_class_names:
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)} defines {node.name}"
                )
            if (
                isinstance(node, ast.FunctionDef)
                and node.name in prohibited_method_names
            ):
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)} defines {node.name}"
                )

    assert offenders == []


def test_paper_execution_contracts_are_not_used_by_runtime_entry_points() -> None:
    runtime_paths = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "adapters/paper_order_preview.py",
        PROJECT_ROOT / "adapters/paper_order_submission.py",
        PROJECT_ROOT / "adapters/scanner_execution.py",
        PROJECT_ROOT / "engine/supervised_brain.py",
        PROJECT_ROOT / "engine/brain.py",
        PROJECT_ROOT / "scanner_engine/automated_scanner.py",
    )
    offenders: list[str] = []
    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")
        if "volcanoes.application.execution" in source:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_qualification_does_not_import_paper_execution_eligibility() -> None:
    violations = _violations(
        _python_files("volcanoes/application/qualification"),
        ("volcanoes.application.execution.eligibility",),
    )

    assert violations == (), "\n".join(violations)


def test_readiness_does_not_import_paper_execution_eligibility() -> None:
    readiness_path = (
        PROJECT_ROOT / "volcanoes/application/qualification/integration/readiness.py"
    )
    violations = _violations(
        (readiness_path,),
        ("volcanoes.application.execution.eligibility",),
    )

    assert violations == (), "\n".join(violations)


def test_paper_execution_eligibility_has_no_outward_dependencies() -> None:
    violations = _violations(
        _python_files("volcanoes/application/execution/eligibility"),
        FORBIDDEN_PAPER_ELIGIBILITY_PREFIXES,
    )

    assert violations == (), "\n".join(violations)


def test_paper_execution_eligibility_has_no_runtime_side_effect_tokens() -> None:
    prohibited_tokens = (
        "os.environ",
        "os.getenv",
        "getenv(",
        "environ[",
        "datetime.now",
        "time.time",
        "random",
        "state/simulated_broker.json",
        "simulated_broker",
        "TradingClient",
        "submit_order",
        "EventPublisher",
        "OperationalMetrics",
    )
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution/eligibility"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_paper_execution_eligibility_defines_no_executor_ports_or_persistence_ports() -> (
    None
):
    prohibited_class_names = {
        "PaperExecutor",
        "PaperExecutionExecutor",
        "PaperBrokerPort",
        "PaperExecutionRepository",
        "PaperExecutionPersistence",
        "ExecutionRuntime",
    }
    prohibited_method_names = {
        "execute",
        "submit",
        "dispatch",
        "reserve",
        "persist",
        "authorize",
        "call_broker",
    }
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution/eligibility"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in prohibited_class_names:
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)} defines {node.name}"
                )
            if (
                isinstance(node, ast.FunctionDef)
                and node.name in prohibited_method_names
            ):
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)} defines {node.name}"
                )

    assert offenders == []


def test_paper_execution_eligibility_has_no_live_symbol() -> None:
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution/eligibility"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in ("LIVE", "PRODUCTION", "REAL_MONEY")
            if token in source
        )

    assert offenders == []


def test_paper_execution_eligibility_is_not_consumed_by_runtime_entry_points() -> None:
    runtime_paths = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "adapters/paper_order_preview.py",
        PROJECT_ROOT / "adapters/paper_order_submission.py",
        PROJECT_ROOT / "adapters/scanner_execution.py",
        PROJECT_ROOT / "engine/supervised_brain.py",
        PROJECT_ROOT / "engine/brain.py",
        PROJECT_ROOT / "scanner_engine/automated_scanner.py",
    )
    offenders: list[str] = []
    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")
        if "PaperExecutionEligibility" in source:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_paper_execution_lifecycle_has_no_outward_dependencies() -> None:
    violations = _violations(
        _python_files("volcanoes/application/execution/lifecycle"),
        FORBIDDEN_PAPER_LIFECYCLE_PREFIXES,
    )

    assert violations == (), "\n".join(violations)


def test_paper_execution_lifecycle_has_no_runtime_side_effect_tokens() -> None:
    prohibited_tokens = (
        "os.environ",
        "os.getenv",
        "getenv(",
        "datetime.now",
        "time.time",
        "random",
        "state/simulated_broker.json",
        "simulated_broker",
        "TradingClient",
        "submit_order",
        "replace_order",
        "cancel_order",
        "EventPublisher",
        "OperationalMetrics",
        "sqlite",
        "open(",
        "write_text",
        "write_bytes",
        "requests",
        "httpx",
        "socket",
    )
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution/lifecycle"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_paper_execution_lifecycle_defines_no_executor_ports_or_persistence_ports() -> (
    None
):
    prohibited_class_names = {
        "PaperExecutor",
        "PaperExecutionExecutor",
        "PaperBrokerPort",
        "PaperExecutionRepository",
        "PaperExecutionPersistence",
        "ExecutionRuntime",
        "DryRunExecutor",
    }
    prohibited_method_names = {
        "execute",
        "submit",
        "reserve",
        "persist",
        "authorize",
        "call_broker",
    }
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution/lifecycle"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in prohibited_class_names:
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)} defines {node.name}"
                )
            if (
                isinstance(node, ast.FunctionDef)
                and node.name in prohibited_method_names
            ):
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)} defines {node.name}"
                )

    assert offenders == []


def test_paper_execution_lifecycle_has_no_live_or_dry_run_state_symbols() -> None:
    prohibited_tokens = (
        "LIVE",
        "PRODUCTION",
        "REAL_MONEY",
        "DRY_RUN_ACCEPTED",
        "DRY_RUN_REJECTED",
        "WORKING",
        "RECOVERED",
    )
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution/lifecycle"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_paper_execution_lifecycle_is_not_wired_into_runtime_entry_points() -> None:
    runtime_paths = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "adapters/paper_order_preview.py",
        PROJECT_ROOT / "adapters/paper_order_submission.py",
        PROJECT_ROOT / "adapters/scanner_execution.py",
        PROJECT_ROOT / "adapters/paper_broker_execution.py",
        PROJECT_ROOT / "broker/simulated.py",
        PROJECT_ROOT / "engine/supervised_brain.py",
        PROJECT_ROOT / "engine/brain.py",
        PROJECT_ROOT / "scanner_engine/automated_scanner.py",
    )
    prohibited_tokens = (
        "PaperExecutionLifecycle",
        "volcanoes.application.execution.lifecycle",
        "PX-TRN-",
    )
    offenders: list[str] = []
    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_paper_execution_dry_run_has_only_approved_dependencies() -> None:
    violations = _violations(
        _python_files("volcanoes/application/execution/dry_run"),
        FORBIDDEN_PAPER_DRY_RUN_PREFIXES,
    )

    assert violations == (), "\n".join(violations)


def test_paper_execution_dry_run_has_no_runtime_side_effect_tokens() -> None:
    prohibited_tokens = (
        "os.environ",
        "os.getenv",
        "getenv(",
        "datetime.now",
        "time.time",
        "random",
        "state/simulated_broker.json",
        "simulated_broker",
        "TradingClient",
        "submit_order",
        "replace_order",
        "cancel_order",
        "EventPublisher",
        "OperationalMetrics",
        "sqlite",
        "open(",
        "write_text",
        "write_bytes",
        "import requests",
        "from requests",
        "import http",
        "from http",
        "socket",
        "subprocess",
    )
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution/dry_run"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_paper_execution_dry_run_defines_no_broker_or_persistence_ports() -> None:
    prohibited_class_names = {
        "PaperBrokerPort",
        "PaperExecutionRepository",
        "PaperExecutionPersistence",
        "BrokerAdapter",
        "ExecutionRuntime",
    }
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution/dry_run"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in prohibited_class_names:
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)} defines {node.name}"
                )

    assert offenders == []


def test_paper_execution_dry_run_has_no_execute_capable_or_live_mode_symbols() -> None:
    prohibited_tokens = (
        "EXECUTE =",
        "BROKER =",
        "LIVE =",
        "PRODUCTION =",
        "REAL =",
        "ACTIVE =",
        "EXECUTED",
        "SUCCESSFULLY_SUBMITTED",
    )
    offenders: list[str] = []
    for path in _python_files("volcanoes/application/execution/dry_run"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_paper_execution_dry_run_is_not_wired_into_runtime_entry_points() -> None:
    runtime_paths = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "adapters/paper_order_preview.py",
        PROJECT_ROOT / "adapters/paper_order_submission.py",
        PROJECT_ROOT / "adapters/scanner_execution.py",
        PROJECT_ROOT / "adapters/paper_broker_execution.py",
        PROJECT_ROOT / "broker/simulated.py",
        PROJECT_ROOT / "engine/supervised_brain.py",
        PROJECT_ROOT / "engine/brain.py",
        PROJECT_ROOT / "scanner_engine/automated_scanner.py",
    )
    prohibited_tokens = (
        "PaperDryRunExecutor",
        "PaperDryRunRequest",
        "volcanoes.application.execution.dry_run",
    )
    offenders: list[str] = []
    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_execution_durability_spike_is_not_imported_by_production_modules() -> None:
    production_paths = _python_files(
        "adapters",
        "broker",
        "engine",
        "scanner_engine",
        "volcanoes",
    ) + (PROJECT_ROOT / "app.py",)
    offenders: list[str] = []
    for path in production_paths:
        source = path.read_text(encoding="utf-8")
        if "spikes.execution_durability" in source:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_execution_durability_spike_does_not_touch_runtime_state_or_brokers() -> None:
    spike_paths = _python_files("spikes/execution_durability")
    violations = _violations(
        spike_paths,
        (
            "adapters",
            "broker",
            "scanner_engine",
            "engine",
            "trading",
            "streamlit",
            "volcanoes.application.supervisor",
            "volcanoes.events",
        ),
    )
    prohibited_tokens = (
        "state/simulated_broker.json",
        "simulated_broker",
        "TradingClient",
        "submit_order",
        "cancel_order",
        "replace_order",
        "LIVE =",
        "PRODUCTION =",
    )
    offenders = list(violations)
    for path in spike_paths:
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {token}"
            for token in prohibited_tokens
            if token in source
        )

    assert offenders == []


def test_paper_execution_persistence_runtime_has_strict_dependency_boundary() -> None:
    path = PROJECT_ROOT / "adapters/paper_execution_persistence_runtime.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    prohibited_roots = {
        "alpaca",
        "broker",
        "config",
        "dotenv",
        "http",
        "requests",
        "scanner_engine",
        "socket",
        "streamlit",
        "urllib",
    }
    assert not any(
        module.split(".", maxsplit=1)[0] in prohibited_roots for module in imports
    )
    prohibited_symbols = {
        "ExecutionPipeline",
        "PaperBrokerExecutionAdapter",
        "SubmitTradeService",
        "getenv",
        "os.environ",
    }
    assert not any(symbol in source for symbol in prohibited_symbols)


def test_paper_execution_persistence_runtime_is_not_implicitly_wired() -> None:
    runtime_module = "adapters.paper_execution_persistence_runtime"
    entry_points = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "main.py",
        PROJECT_ROOT / "scanner_engine/automated_scanner.py",
        PROJECT_ROOT / "engine/supervised_brain.py",
    )

    assert all(
        runtime_module not in path.read_text(encoding="utf-8") for path in entry_points
    )


def test_transactional_intake_is_brokerless_and_storage_neutral() -> None:
    paths = tuple(
        sorted((PROJECT_ROOT / "volcanoes/application/execution/intake").glob("*.py"))
    )
    assert _violations(paths, FORBIDDEN_TRANSACTIONAL_INTAKE_PREFIXES) == ()

    prohibited_tokens = (
        "submit_order",
        "cancel_order",
        "replace_order",
        "call_broker",
        "ExecutionPipeline",
        "PaperBrokerExecutionAdapter",
        "PaperExecutionPersistenceRuntime",
        "sqlite3",
        "state/",
    )
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)} contains {token}"
        for path in paths
        for token in prohibited_tokens
        if token in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_paper_certification_package_is_offline_and_storage_neutral() -> None:
    paths = _python_files("volcanoes/application/execution/certification")

    assert _violations(paths, FORBIDDEN_CERTIFICATION_PREFIXES) == ()


def test_paper_certification_package_exposes_no_effect_capabilities() -> None:
    paths = _python_files("volcanoes/application/execution/certification")
    prohibited_symbols = (
        "def submit",
        "def cancel",
        "def replace",
        "def query",
        "def retry",
        "def reconcile",
        "submit(",
        "cancel(",
        "replace(",
        "query(",
        "retry(",
        "reconcile(",
        "transactionprovider",
        "persistenceprovider",
        "credentialprovider",
        "runtimecomposition",
        "executionpipeline",
        "simulatorport",
        "scannerport",
        "supervisorport",
    )
    offenders = []
    for path in paths:
        source = path.read_text(encoding="utf-8").lower()
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)} contains {symbol}"
            for symbol in prohibited_symbols
            if symbol in source
        )

    assert offenders == []


def test_controlled_submission_package_is_broker_neutral_and_uses_only_storage_neutral_ports() -> (
    None
):
    paths = _python_files("volcanoes/application/execution/submission")

    assert _violations(paths, FORBIDDEN_CONTROLLED_SUBMISSION_PREFIXES) == ()


def test_controlled_submission_is_not_wired_into_existing_runtime_paths() -> None:
    prohibited_module = "volcanoes.application.execution.submission"
    paths = (
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "adapters/paper_broker_execution.py",
        PROJECT_ROOT / "adapters/paper_execution_persistence_runtime.py",
        PROJECT_ROOT / "volcanoes/application/services/submit_trade.py",
        PROJECT_ROOT / "volcanoes/application/supervisor/supervisor.py",
    )

    assert all(
        prohibited_module not in path.read_text(encoding="utf-8") for path in paths
    )


def test_controlled_submission_defines_no_runtime_or_effect_implementation() -> None:
    paths = _python_files("volcanoes/application/execution/submission")
    prohibited_symbols = (
        "sqlite3",
        "requests",
        "socket",
        "getenv",
        "environ",
        "alpaca",
        "tradingclient",
        "paperbrokerexecutionadapter",
        "executionpipeline",
        "submittradeservice",
        "retry_policy",
        "reconcile",
        "query_status",
    )
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)} contains {symbol}"
        for path in paths
        for symbol in prohibited_symbols
        if symbol in path.read_text(encoding="utf-8").lower()
    ]

    assert offenders == []
