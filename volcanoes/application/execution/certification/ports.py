"""Pure callable boundaries for offline certification."""

from __future__ import annotations

from typing import Protocol

from volcanoes.application.execution.certification.contracts import (
    MappedRequest,
    NormalizedFailure,
    NormalizedObservation,
    SyntheticOrderFixture,
    SyntheticResponseFixture,
)


class CertificationRequestMapper(Protocol):
    """Map a synthetic fixture without causing an external effect."""

    def __call__(self, fixture: SyntheticOrderFixture) -> MappedRequest: ...


class CertificationResponseNormalizer(Protocol):
    """Normalize synthetic response data without querying an external system."""

    def __call__(
        self, fixture: SyntheticResponseFixture
    ) -> NormalizedObservation | NormalizedFailure: ...
