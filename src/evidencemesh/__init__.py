"""Evidence-first web research infrastructure for AI agents."""

from evidencemesh.config import DeploymentProfile
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
    "DeploymentProfile",
    "EvidenceMesh",
    "FetchRequest",
    "FetchedDocument",
    "ResearchPacket",
    "ResearchRequest",
    "SearchRequest",
    "SearchResponse",
]
__version__ = "0.1.0"
