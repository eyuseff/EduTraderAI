"""Safe errors for Paper qualification integration translation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QualificationIntegrationError(Exception):
    """Base integration error with safe structured metadata."""

    reason_code: str
    safe_message: str
    context: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValueError("reason_code cannot be empty.")
        if not isinstance(self.safe_message, str) or not self.safe_message.strip():
            raise ValueError("safe_message cannot be empty.")
        object.__setattr__(
            self,
            "context",
            tuple(sorted((str(key), str(value)) for key, value in self.context)),
        )
        Exception.__init__(self, self.safe_message)

    def __str__(self) -> str:
        return self.safe_message


class PaperEnvironmentRequiredError(QualificationIntegrationError):
    """Raised when an integration input is not explicitly Paper-only."""


class UnsupportedRuntimeRequestError(QualificationIntegrationError):
    """Raised when a runtime request cannot be translated safely."""


class RuntimeRequestValidationError(QualificationIntegrationError):
    """Raised when a runtime request is structurally invalid."""


class UnsupportedExecutionPlanError(QualificationIntegrationError):
    """Raised when an execution plan cannot become a runtime action request."""


class UnsupportedRuntimeObservationError(QualificationIntegrationError):
    """Raised when a normalized observation has no safe qualification mapping."""


class IntegrationIdentityError(QualificationIntegrationError):
    """Raised when deterministic integration identity cannot be derived."""


class IntegrationTranslationError(QualificationIntegrationError):
    """Raised when a safe translation cannot be completed."""


class UnsafeIntegrationMetadataError(QualificationIntegrationError):
    """Raised when integration metadata cannot be made safe."""


class PaperQualificationFacadeError(QualificationIntegrationError):
    """Raised when facade orchestration cannot complete safely."""


class FacadeIdentityContinuityError(PaperQualificationFacadeError):
    """Raised when service output conflicts with the originating request."""


class FacadeResultValidationError(PaperQualificationFacadeError):
    """Raised when a service result cannot be represented by the facade."""


class FacadeServiceInvocationError(PaperQualificationFacadeError):
    """Raised when the injected application service fails."""
