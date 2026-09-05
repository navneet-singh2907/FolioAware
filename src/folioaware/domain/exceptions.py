"""Stable domain exceptions mapped by entry points."""


class FolioAwareError(Exception):
    """Base class for expected FolioAware failures."""


class ConfigurationError(FolioAwareError):
    """Required configuration is missing or incompatible."""


class KnowledgeUnavailableError(FolioAwareError):
    """The active knowledge version cannot be read safely."""


class ModelUnavailableError(FolioAwareError):
    """A required model dependency is unavailable or timed out."""

    def __init__(
        self,
        message: str = "model dependency unavailable",
        *,
        provider_error_type: str | None = None,
        provider_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_error_type = provider_error_type
        self.provider_status = provider_status


class InsightsUnavailableError(FolioAwareError):
    """Privacy-reduced telemetry or aggregate insights are unavailable."""


class InvalidModelOutputError(FolioAwareError):
    """A model candidate failed schema or citation validation."""


class SyncConflictError(FolioAwareError):
    """The active version changed while a candidate was being activated."""


class SyncValidationError(FolioAwareError):
    """A candidate knowledge version failed validation."""
