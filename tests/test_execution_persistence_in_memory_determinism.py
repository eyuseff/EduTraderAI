from __future__ import annotations

import ast
from pathlib import Path

from volcanoes.application.execution import (
    InMemoryExecutionPersistence,
    PaperExecutionRevision,
)
from test_execution_persistence_in_memory_repositories import (
    aggregate_record,
    command_record,
    idempotency_record,
    transition_record,
)

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "volcanoes/application/execution/persistence/in_memory"
)


def _run_sequence() -> tuple[object, ...]:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    uow.commands.register(command_record("MSFT"))
    uow.idempotency.reserve(idempotency_record("MSFT"))
    uow.aggregates.save(
        aggregate_record("MSFT"), expected_revision=PaperExecutionRevision.initial()
    )
    uow.transitions.append(transition_record("MSFT"))
    result = uow.commit()
    snapshot = store.snapshot()
    return (
        result.to_primitive(),
        tuple(record.to_primitive() for record in snapshot.command_records()),
        tuple(record.to_primitive() for record in snapshot.idempotency_records()),
        tuple(record.to_primitive() for record in snapshot.aggregate_records()),
        tuple(record.to_primitive() for record in snapshot.transition_records()),
    )


def test_same_operations_produce_same_final_state() -> None:
    assert _run_sequence() == _run_sequence()


def test_deterministic_order_does_not_depend_on_python_dict_insertion() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    for symbol in ("TSLA", "AAPL", "MSFT"):
        uow.aggregates.save(
            aggregate_record(symbol), expected_revision=PaperExecutionRevision.initial()
        )
    uow.commit()

    values = [
        record.aggregate_id.value for record in store.snapshot().aggregate_records()
    ]
    assert values == sorted(values)


def test_transition_order_is_append_order() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    uow.transitions.append(transition_record("AAPL", 1))
    uow.transitions.append(transition_record("AAPL", 2))
    uow.commit()

    assert [
        record.transition_record_id for record in store.snapshot().transition_records()
    ] == [
        "transition-record-AAPL-1",
        "transition-record-AAPL-2",
    ]


def test_in_memory_package_has_no_clock_random_environment_or_file_access_tokens() -> (
    None
):
    prohibited = (
        "datetime.now",
        "datetime.utcnow",
        "time.time",
        "uuid4",
        "random",
        "secrets",
        "urandom",
        "os.environ",
        "os.getenv",
        "getenv(",
        "open(",
        "Path(",
        "read_text",
        "write_text",
        "write_bytes",
        "json.dump",
        "jsonlines",
    )
    offenders = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.name} contains {token}" for token in prohibited if token in source
        )

    assert offenders == []


def test_in_memory_package_has_no_forbidden_imports() -> None:
    prohibited_roots = {
        "sqlite3",
        "psycopg",
        "sqlalchemy",
        "redis",
        "os",
        "pathlib",
        "datetime",
        "time",
        "uuid",
        "random",
        "secrets",
        "threading",
        "multiprocessing",
        "subprocess",
        "requests",
        "http",
        "socket",
        "logging",
    }
    offenders = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in prohibited_roots:
                        offenders.append(f"{path.name} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".")[0] in prohibited_roots:
                    offenders.append(f"{path.name} imports {module}")

    assert offenders == []


def test_in_memory_package_does_not_reference_runtime_state_or_authority() -> None:
    prohibited = (
        "state/simulated_broker.json",
        "simulated_broker",
        "TradingClient",
        "submit_order",
        "cancel_order",
        "EventPublisher",
        "OperationalMetrics",
        "LIVE",
        "PRODUCTION",
        "execution authorized",
    )
    offenders = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.name} contains {token}" for token in prohibited if token in source
        )

    assert offenders == []
