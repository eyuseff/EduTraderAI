"""Release hardening tests for startup configuration and health diagnostics."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from volcanoes.application.platform import (
    BrokerMode,
    ConfigurationError,
    CredentialStatus,
    DeterministicFeatureFlags,
    PlatformConfiguration,
    ScannerExecutionMode,
    TradingPolicyConfiguration,
    build_platform_health_report,
    validate_broker_runtime,
    validate_configuration,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def configuration(
    *,
    flags: DeterministicFeatureFlags | None = None,
    policy: TradingPolicyConfiguration | None = None,
    broker_mode: BrokerMode = BrokerMode.SIMULATED_PAPER,
    scanner_mode: ScannerExecutionMode | None = None,
    credentials: CredentialStatus | None = None,
) -> PlatformConfiguration:
    configured_flags = flags or DeterministicFeatureFlags()
    return PlatformConfiguration(
        feature_flags=configured_flags,
        policy=policy or TradingPolicyConfiguration(),
        broker_mode=broker_mode,
        scanner_execution_mode=scanner_mode
        or (
            ScannerExecutionMode.SUPERVISED
            if configured_flags.scanner
            else ScannerExecutionMode.LEGACY_ROLLBACK
        ),
        credentials=credentials or CredentialStatus(),
    )


def test_default_release_configuration_is_valid() -> None:
    configured = configuration()

    assert validate_configuration(configured) is configured
    validate_broker_runtime(configured, broker_is_paper=True)


@pytest.mark.parametrize(
    "flags",
    [
        DeterministicFeatureFlags(preview=True, submission=False),
        DeterministicFeatureFlags(preview=False, submission=True),
    ],
)
def test_mixed_manual_execution_generations_fail_closed(
    flags: DeterministicFeatureFlags,
) -> None:
    with pytest.raises(ConfigurationError, match="must change together"):
        validate_configuration(configuration(flags=flags))


def test_full_manual_rollback_is_valid() -> None:
    flags = DeterministicFeatureFlags(
        preview=False,
        submission=False,
        scanner=True,
    )

    assert validate_configuration(configuration(flags=flags)).feature_flags == flags


def test_scanner_mode_must_match_rollback_flag() -> None:
    flags = DeterministicFeatureFlags(scanner=False)

    with pytest.raises(ConfigurationError, match="conflicts"):
        validate_configuration(
            configuration(
                flags=flags,
                scanner_mode=ScannerExecutionMode.SUPERVISED,
            )
        )


def test_simulator_does_not_require_alpaca_credentials() -> None:
    assert (
        validate_configuration(
            configuration(credentials=CredentialStatus())
        ).broker_mode
        is BrokerMode.SIMULATED_PAPER
    )


@pytest.mark.parametrize(
    "credentials",
    [
        CredentialStatus(),
        CredentialStatus(alpaca_api_key_present=True),
        CredentialStatus(alpaca_secret_key_present=True),
    ],
)
def test_alpaca_requires_both_credentials(credentials: CredentialStatus) -> None:
    with pytest.raises(ConfigurationError, match="requires both"):
        validate_configuration(
            configuration(
                broker_mode=BrokerMode.ALPACA_PAPER,
                credentials=credentials,
            )
        )


def test_alpaca_configuration_accepts_both_credentials() -> None:
    configured = configuration(
        broker_mode=BrokerMode.ALPACA_PAPER,
        credentials=CredentialStatus(True, True),
    )

    assert validate_configuration(configured) is configured


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("risk_per_trade_pct", Decimal("0"), "within"),
        ("max_daily_loss_pct", Decimal("101"), "within"),
        ("max_open_positions", 0, "at least 1"),
        ("minimum_reward_risk", Decimal("0"), "positive"),
        ("minimum_price", Decimal("0"), "positive"),
        ("long_only", False, "long_only=True"),
    ],
)
def test_invalid_policy_configuration_fails_before_execution(
    field: str,
    value: object,
    message: str,
) -> None:
    overrides: dict[str, Any] = {field: value}
    policy = replace(TradingPolicyConfiguration(), **overrides)

    with pytest.raises(ConfigurationError, match=message):
        validate_configuration(configuration(policy=policy))


def test_single_position_limit_cannot_exceed_total_exposure() -> None:
    policy = replace(
        TradingPolicyConfiguration(),
        max_single_position_pct=Decimal("60"),
    )

    with pytest.raises(ConfigurationError, match="cannot exceed"):
        validate_configuration(configuration(policy=policy))


def test_non_paper_runtime_fails_before_execution() -> None:
    with pytest.raises(ConfigurationError, match="not paper-only"):
        validate_broker_runtime(configuration(), broker_is_paper=False)


def test_health_report_exposes_active_paths_flags_and_limitations() -> None:
    report = build_platform_health_report(
        configuration(),
        event_publisher_type="NullEventPublisher",
    )

    assert report.release == "4.0.0-rc1"
    assert report.active_execution_paths == (
        "manual_deterministic_preview",
        "manual_deterministic_submission",
        "supervised_scanner_preview_only",
        "supervised_scanner_submission",
    )
    assert report.rollback_execution_paths == (
        "legacy_manual_preview_and_submission",
        "legacy_scanner_preview_and_submission",
    )
    assert dict(report.deterministic_flags) == {
        "preview": True,
        "scanner": True,
        "submission": True,
    }
    assert report.event_publisher_type == "NullEventPublisher"
    assert report.persistence_mode == "LOCAL_JSON_BROKER_STATE"
    assert report.supervisor_state_mode == "PROCESS_LOCAL_IN_MEMORY"
    assert report.scanner_execution_mode == "SUPERVISED"
    assert report.known_operational_limitations


def test_health_report_exposes_every_legacy_rollback_path() -> None:
    flags = DeterministicFeatureFlags(False, False, False)
    report = build_platform_health_report(
        configuration(flags=flags),
        event_publisher_type="NullEventPublisher",
    )

    assert report.active_execution_paths == (
        "legacy_manual_preview",
        "legacy_manual_submission",
        "legacy_scanner_preview_only",
        "legacy_scanner_submission",
    )
    assert report.scanner_execution_mode == "LEGACY_ROLLBACK"
    assert dict(report.deterministic_flags) == {
        "preview": False,
        "scanner": False,
        "submission": False,
    }


@pytest.mark.parametrize(
    "value",
    [
        DeterministicFeatureFlags(),
        TradingPolicyConfiguration(),
        CredentialStatus(),
        configuration(),
        build_platform_health_report(
            configuration(),
            event_publisher_type="NullEventPublisher",
        ),
    ],
)
def test_configuration_and_health_contracts_are_immutable(value: object) -> None:
    with pytest.raises(FrozenInstanceError):
        value.changed = True  # type: ignore[attr-defined]


def test_health_module_has_no_streamlit_or_broker_dependency() -> None:
    source = (PROJECT_ROOT / "volcanoes/application/platform/health.py").read_text(
        encoding="utf-8"
    )
    imports: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert not any(module.startswith("streamlit") for module in imports)
    assert not any(
        module == "broker" or module.startswith("broker.") for module in imports
    )


def test_app_validates_configuration_before_broker_composition() -> None:
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    assert source.index("validate_configuration(startup_configuration)") < source.index(
        "AlpacaPaperBroker()"
    )
    assert "validate_broker_runtime(" in source
    assert "Startup configuration is invalid" in source
    assert "st.stop()" in source
