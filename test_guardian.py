from volcanoes.guardian.guardian import Guardian
from volcanoes.scanner.explorer import Explorer


def main() -> None:
    explorer = Explorer()
    guardian = Guardian(minimum_score=80)

    symbols = ["AAPL", "MSFT", "NVDA", "META", "AMZN"]
    candidates = explorer.scan_symbols(symbols)

    print("\n===== Guardian Decisions =====\n")

    for candidate, decision in guardian.evaluate_many(candidates):
        status = "APPROVED" if decision.approved else "REJECTED"

        print(
            f"{candidate.symbol:5} | "
            f"Score: {candidate.score:3} | "
            f"{status}"
        )
        print(f"Reason: {decision.reason}")
        print("-" * 60)


if __name__ == "__main__":
    main()
