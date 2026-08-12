"""Risk management exceptions."""


class RiskViolation(Exception):
    """Raised when a trade violates a risk rule."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
