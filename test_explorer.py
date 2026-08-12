from volcanoes.database.repository import SQLiteRepository
from volcanoes.database.schema import initialize_database
from volcanoes.scanner.explorer import Explorer


def main() -> None:
    initialize_database()

    explorer = Explorer()
    repository = SQLiteRepository()

    candidate = explorer.evaluate_symbol("AAPL")
    candidate_id = repository.save_candidate(candidate)

    print("Candidate ID:", candidate_id)
    print("Symbol:", candidate.symbol)
    print("Score:", candidate.score)
    print("Entry price:", candidate.entry_price)
    print("Explanation:", candidate.explanation)
    print("Candidates in database:", repository.count_rows("candidates"))


if __name__ == "__main__":
    main()
