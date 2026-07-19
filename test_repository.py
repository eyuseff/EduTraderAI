from volcanoes.database.models import Candidate
from volcanoes.database.repository import SQLiteRepository
from volcanoes.database.schema import initialize_database


def main() -> None:
    initialize_database()

    repository = SQLiteRepository()

    candidate = Candidate(
        symbol="NVDA",
        strategy_name="Momentum",
        score=85,
    )

    candidate_id = repository.save_candidate(candidate)

    print(f"Candidate saved with ID: {candidate_id}")
    print(
        "Candidates in database:",
        repository.count_rows("candidates"),
    )


if __name__ == "__main__":
    main()
