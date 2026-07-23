"""Worker-level failure contracts owned by the Celery execution boundary."""


class RetryableTaskError(Exception):
    """A transient, idempotently retryable task failure."""
