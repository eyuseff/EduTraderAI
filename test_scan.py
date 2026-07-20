from volcanoes.scanner.explorer import Explorer


def main():
    explorer = Explorer()

    symbols = [
        "AAPL",
        "MSFT",
        "NVDA",
        "META",
        "AMZN",
    ]

    candidates = explorer.scan_symbols(symbols)

    print("\n===== Scan Results =====\n")

    for candidate in candidates:
        print(
            f"{candidate.symbol:5} | "
            f"Score: {candidate.score:3} | "
            f"Price: {candidate.entry_price:.2f}"
        )
        print(f"Reason: {candidate.explanation}")
        print("-" * 60)


if __name__ == "__main__":
    main()
