"""
EduTrader AI
Ranking Engine

Ranks analyzed stocks from strongest to weakest opportunity.
"""


class RankingEngine:
    """Sorts stocks using score and confidence."""

    @staticmethod
    def rank(market: list[dict]) -> list[dict]:
        """
        Rank stocks from strongest to weakest.

        Primary criterion:
        - Highest AI score

        Tie-breakers:
        - Highest confidence
        - Highest risk/reward ratio
        - Symbol alphabetically
        """

        return sorted(
            market,
            key=lambda stock: (
                -float(stock.get("Score", 0)),
                -float(stock.get("Confidence", 0)),
                -float(stock.get("RiskReward", 0)),
                str(stock.get("Symbol", "")),
            ),
        )