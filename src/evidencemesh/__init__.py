"""Evidence-first web research infrastructure for AI agents."""

from evidencemesh.citations import CitationAudit, audit_citations
from evidencemesh.config import DeploymentProfile
from evidencemesh.engine import EvidenceMesh
from evidencemesh.governor import (
    ClosedAlphaPolicy,
    ClosedAlphaSession,
    DispatchIntent,
    SQLiteBudgetGovernor,
)
from evidencemesh.models import (
    FetchedDocument,
    FetchRequest,
    ResearchPacket,
    ResearchRequest,
    SearchRequest,
    SearchResponse,
)

__all__ = [
    "CitationAudit",
    "ClosedAlphaPolicy",
    "ClosedAlphaSession",
    "DeploymentProfile",
    "DispatchIntent",
    "EvidenceMesh",
    "FetchRequest",
    "FetchedDocument",
    "ResearchPacket",
    "ResearchRequest",
    "SQLiteBudgetGovernor",
    "SearchRequest",
    "SearchResponse",
    "audit_citations",
]
__version__ = "0.1.0"
