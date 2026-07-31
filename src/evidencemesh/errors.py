"""Domain-specific exceptions exposed by EvidenceMesh."""

from __future__ import annotations


class EvidenceMeshError(Exception):
    """Base error for predictable EvidenceMesh failures."""


class ConfigurationError(EvidenceMeshError):
    """Raised when runtime configuration is invalid."""


class BudgetConfigurationError(ConfigurationError):
    """Raised when the closed-alpha governor cannot guarantee safe dispatch."""


class BudgetExceededError(EvidenceMeshError):
    """Raised before dispatch when a closed-alpha hard limit would be exceeded."""


class ProviderError(EvidenceMeshError):
    """Raised when a search provider cannot satisfy a request."""

    def __init__(
        self,
        message: str,
        *,
        kind: str = "provider_error",
        upstream_engines: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.upstream_engines = tuple(
            dict.fromkeys(engine for engine in upstream_engines if engine)
        )


class ProviderCircuitOpenError(ProviderError):
    """Raised when a provider call is skipped by its reliability circuit."""

    def __init__(self, message: str) -> None:
        super().__init__(message, kind="circuit_open")


class FetchError(EvidenceMeshError):
    """Raised when a document cannot be fetched safely."""


class UnsafeURLError(FetchError):
    """Raised when a URL violates the outbound request policy."""


class UnsupportedContentError(FetchError):
    """Raised when a response type cannot be extracted."""
