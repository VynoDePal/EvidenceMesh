"""Evidence-first web research infrastructure for AI agents."""

from evidencemesh.alpha_liveness import (
    A2RetentionSupervisor,
    A2SQLiteAlphaControlPlane,
    A2SQLiteBudgetGovernor,
    FeedbackPublicationAuthority,
    GovernedAsyncTransport,
    SupervisorLease,
)
from evidencemesh.citations import CitationAudit, audit_citations
from evidencemesh.closed_alpha_feedback import (
    ClosedAlphaFeedbackContract,
    ClosedAlphaFeedbackIdentity,
    ClosedAlphaFeedbackStore,
    FeedbackContext,
    FeedbackRetentionScheduler,
    FeedbackStoreBinding,
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
    "A2RetentionSupervisor",
    "A2SQLiteAlphaControlPlane",
    "A2SQLiteBudgetGovernor",
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
    "FeedbackPublicationAuthority",
    "FeedbackRetentionScheduler",
    "FeedbackStoreBinding",
    "FetchRequest",
    "FetchedDocument",
    "GovernedAsyncTransport",
    "ResearchPacket",
    "ResearchRequest",
    "SQLiteAlphaControlPlane",
    "SQLiteBudgetGovernor",
    "SearchRequest",
    "SearchResponse",
    "SupervisorLease",
    "audit_citations",
]
__version__ = "0.1.0"
