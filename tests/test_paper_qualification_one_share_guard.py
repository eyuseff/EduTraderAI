from __future__ import annotations

import pytest

from test_paper_qualification_integration_contracts import order_intent, runtime_request
from volcanoes.application.qualification.integration import RuntimeRequestValidationError
from volcanoes.application.qualification.integration.order_safety import (
    require_one_share_order_intent,
)
from volcanoes.application.qualification.integration.translation import (
    runtime_request_to_qualification_command,
)


def test_exactly_one_share_reaches_qualification_translation() -> None:
    request = runtime_request(order_intent=order_intent(quantity=1))

    command = runtime_request_to_qualification_command(request)

    assert command.qualification_run_id == request.qualification_run_id


@pytest.mark.parametrize("quantity", (2, 10, 1_000_000))
def test_larger_quantity_is_blocked_before_qualification_translation(
    quantity: int,
) -> None:
    request = runtime_request(order_intent=order_intent(quantity=quantity))

    with pytest.raises(RuntimeRequestValidationError) as error_info:
        runtime_request_to_qualification_command(request)

    assert error_info.value.reason_code == "QUALIFICATION_ONE_SHARE_REQUIRED"


def test_missing_order_intent_remains_valid_for_non_order_events() -> None:
    request = runtime_request(order_intent=None)

    command = runtime_request_to_qualification_command(request)

    assert command.qualification_run_id == request.qualification_run_id


def test_guard_is_idempotent_for_one_share_intent() -> None:
    intent = order_intent(quantity=1)

    assert require_one_share_order_intent(intent) is intent
    assert require_one_share_order_intent(intent) is intent
