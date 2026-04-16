"""User-actionable configuration and wiring errors."""


class LangchainConfigError(ValueError):
    """Raised when ``BUB_LANGCHAIN_*`` settings are inconsistent or incomplete."""
