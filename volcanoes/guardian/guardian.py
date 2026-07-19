"""Risk-control engine for Volcanes — The Real Volcanoes."""

from __future__ import annotations

from volcanoes.domain import Candidate, GuardianDecision


class Guardian:
    """Apply deterministic risk rules before execution."""

    def __init__(
        self,
        minimum_score: int = 80,
        maximum_entry_price: float | None = None,
    ) -> None:
        if not 0 <= minimum_score <= 100:
            raise ValueError("Minimum score must be between 0 and 100.")

        if maximum_entry_price is not None and maximum_entry_price <= 0:
            raise ValueError(
                "Maximum entry price must be greater than zero."
            )

        self.minimum_score = minimum_score
        self.maximum_entry_price = maximum_entry_price

    def evaluate(self, candidate: Candidate) -> GuardianDecision:
        """Approve or reject one candidate using explicit rules."""

        if candidate.entry_price is None:
            return GuardianDecision.reject(
                reason="Candidate has no entry price.",
                risk_score=candidate.score,
            )

        if candidate.score < self.minimum_score:
            return GuardianDecision.reject(
                reason=(
                    f"Candidate score {candidate.score} is below "
                    f"Guardian minimum score {self.minimum_score}."
                ),
                risk_score=candidate.score,
            )

        if (
            self.maximum_entry_price is not None
            and candidate.entry_price > self.maximum_entry_price
        ):
            return GuardianDecision.reject(
                reason=(
                    f"Candidate entry price {candidate.entry_price:.2f} "
                    f"exceeds Guardian maximum entry price "
                    f"{self.maximum_entry_price:.2f}."
                ),
                risk_score=candidate.score,
            )

        return GuardianDecision.approve(
            reason=(
                f"Candidate approved with score {candidate.score}. "
                "All Guardian risk rules passed."
            ),
            risk_score=candidate.score,
        )

    def evaluate_many(
        self,
        candidates: list[Candidate],
    ) -> list[tuple[Candidate, GuardianDecision]]:
        """Evaluate multiple candidates while preserving their order."""

        return [
            (candidate, self.evaluate(candidate))
            for candidate in candidates
        ]
