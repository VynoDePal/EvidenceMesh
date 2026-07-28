"""Domain-specific exceptions exposed by EvidenceMesh."""


class EvidenceMeshError(Exception):
    """Base error for predictable EvidenceMesh failures."""


class ConfigurationError(EvidenceMeshError):
    """Raised when runtime configuration is invalid."""


class ProviderError(EvidenceMeshError):
    """Raised when a search provider cannot satisfy a request."""


class FetchError(EvidenceMeshError):
    """Raised when a document cannot be fetched safely."""


class UnsafeURLError(FetchError):
    """Raised when a URL violates the outbound request policy."""


class UnsupportedContentError(FetchError):
    """Raised when a response type cannot be extracted."""
