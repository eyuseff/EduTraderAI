"""Supervisor-level operational events."""

from __future__ import annotations

from dataclasses import dataclass

from volcanoes.events import DomainEvent, PolicyConfiguration


@dataclass(frozen=True, slots=True, kw_only=True)
class SupervisorEvent(DomainEvent):
    """Base event for one supervised execution lifecycle."""

    idempotency_key: str
    symbol: str
    source: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionStarted(SupervisorEvent):
    policy: str = "ExecutionSupervisor"


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionSkipped(SupervisorEvent):
    code: str
    policy: str
    explanation: str
    configuration: PolicyConfiguration = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionCompleted(SupervisorEvent):
    order_id: str | None
    quantity: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionAborted(SupervisorEvent):
    code: str
    policy: str
    explanation: str
    configuration: PolicyConfiguration = ()
