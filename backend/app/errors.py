"""Errors a step handler can raise to tell the engine what to do next."""


class StepError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TransientError(StepError):
    """Worth retrying: timeouts, rate limits, a flaky upstream."""


class PermanentError(StepError):
    """Retrying won't help: bad input, missing data, a rejected request."""
