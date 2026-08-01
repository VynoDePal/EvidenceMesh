"""Evidence-first web research infrastructure for AI agents."""

from evidencemesh.citations import CitationAudit, audit_citations
from evidencemesh.closed_alpha_feedback import (
    ClosedAlphaFeedbackContract,
    ClosedAlphaFeedbackIdentity,
    ClosedAlphaFeedbackStore,
    FeedbackContext,
    FeedbackRetentionScheduler,
)
from evidencemesh.config import DeploymentProfile
from evidencemesh.engine import EvidenceMesh
from evidencemesh.governor import (
    AlphaControlState,
    ClosedAlphaAdmission,
    ClosedAlphaPolicy,
    ClosedAlphaSession,
    DispatchIntent,
    SQLiteAlphaControlPlane,
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
    "AlphaControlState",
    "CitationAudit",
    "ClosedAlphaAdmission",
    "ClosedAlphaFeedbackContract",
    "ClosedAlphaFeedbackIdentity",
    "ClosedAlphaFeedbackStore",
    "ClosedAlphaPolicy",
    "ClosedAlphaSession",
    "DeploymentProfile",
    "DispatchIntent",
    "EvidenceMesh",
    "FeedbackContext",
    "FeedbackRetentionScheduler",
    "FetchRequest",
    "FetchedDocument",
    "ResearchPacket",
    "ResearchRequest",
    "SQLiteAlphaControlPlane",
    "SQLiteBudgetGovernor",
    "SearchRequest",
    "SearchResponse",
    "audit_citations",
]
__version__ = "0.1.0"
