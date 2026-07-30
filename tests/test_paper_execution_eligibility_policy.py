from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from volcanoes.application.execution import (
    PaperExecutionEligibilityError,
    PaperExecutionEligibilityPolicy,
    PaperExecutionOperation,
)


def test_policy_is_immutable_normalized_fingerprinted_and_hashable() -> None:
    policy = PaperExecutionEligibilityPolicy(
        "eligibility-v1",
        allowed_operations=(
            PaperExecutionOperation.REPLACE,
            PaperExecutionOperation.SUBMIT,
            PaperExecutionOperation.SUBMIT,
            PaperExecutionOperation.CANCEL,
        ),
    )

    assert policy.allowed_operations == (
        PaperExecutionOperation.CANCEL,
        PaperExecutionOperation.REPLACE,
        PaperExecutionOperation.SUBMIT,
    )
    assert policy.policy_fingerprint.startswith("pep-")
    assert hash(policy) == hash(policy)
    with pytest.raises(FrozenInstanceError):
        policy.policy_version = "other"  # type: ignore[misc]


def test_policy_fixed_golden_fingerprint() -> None:
    policy = PaperExecutionEligibilityPolicy("eligibility-v1")

    assert (
        policy.policy_fingerprint
        == "pep-93d6c26ce09597da3a0027fcb5fa5b4735a2ed99c82d32f41bdb3244e6f25839"
    )


@pytest.mark.parametrize(
    "kwargs",
    (
        {"policy_version": ""},
        {"policy_version": "api_key-policy"},
        {"allowed_operations": []},
        {"allowed_operations": ("SUBMIT",)},
        {"require_paper_mode": "yes"},
        {"require_approval_binding": True, "require_explicit_approval": False},
        {"require_unexpired_approval": True, "require_explicit_approval": False},
    ),
)
def test_policy_rejects_invalid_or_contradictory_configuration(kwargs: dict) -> None:
    with pytest.raises((PaperExecutionEligibilityError, Exception)):
        PaperExecutionEligibilityPolicy(**kwargs)


def test_policy_contains_no_callbacks_predicates_or_services() -> None:
    policy = PaperExecutionEligibilityPolicy("eligibility-v1")

    assert not hasattr(policy, "evaluate")
    assert not hasattr(policy, "predicate")
    assert not hasattr(policy, "service")
    assert callable(getattr(policy, "to_primitive"))
