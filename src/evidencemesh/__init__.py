"""Evidence-first web research infrastructure for AI agents."""

from evidencemesh.engine import EvidenceMesh
from evidencemesh.models import (
    FetchedDocument,
    FetchRequest,
    ResearchPacket,
    ResearchRequest,
    SearchRequest,
    SearchResponse,
)

__all__ = [
    "EvidenceMesh",
    "FetchRequest",
    "FetchedDocument",
    "ResearchPacket",
    "ResearchRequest",
    "SearchRequest",
    "SearchResponse",
]
__version__ = "0.1.0"
