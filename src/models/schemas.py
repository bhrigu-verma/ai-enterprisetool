"""Domain models shared across all layers."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Source types
# ---------------------------------------------------------------------------

class SourceType(str, enum.Enum):
    PR_DESCRIPTION = "pr_description"
    PR_COMMENT = "pr_comment"
    COMMIT = "commit"
    SLACK_THREAD = "slack_thread"
    TICKET = "ticket"
    DOCUMENT = "document"
    CODE = "code"


class QuestionType(str, enum.Enum):
    WHY = "why"
    HOW = "how"
    WHO = "who"
    WHAT_BROKE = "what_broke"
    FACTUAL = "factual"
    GENERAL = "general"


# ---------------------------------------------------------------------------
# Chunk & metadata
# ---------------------------------------------------------------------------

class ChunkMetadata(BaseModel):
    """Rich metadata attached to every ingested chunk."""

    source_type: SourceType
    source_id: str
    author: str = ""
    timestamp: datetime | None = None
    age_days: int = 0
    linked_entities: list[str] = Field(default_factory=list)
    repo: str = ""
    tags: list[str] = Field(default_factory=list)
    is_likely_outdated: bool = False
    permissions: list[str] = Field(default_factory=list)


class Chunk(BaseModel):
    """A semantically meaningful unit of ingested content."""

    id: str
    content: str
    metadata: ChunkMetadata
    embedding: list[float] | None = None
    staleness_score: float = 0.0
    staleness_reason: str = ""


# ---------------------------------------------------------------------------
# Ingestion data
# ---------------------------------------------------------------------------

class PRData(BaseModel):
    """Normalised pull request data from any SCM provider."""

    pr_id: str
    repo: str
    title: str
    description: str = ""
    author: str = ""
    merged_by: str = ""
    comments: list[str] = Field(default_factory=list)
    linked_issues: list[str] = Field(default_factory=list)
    timestamp: datetime | None = None
    diff_summary: str = ""


class CommitData(BaseModel):
    """Normalised commit data."""

    sha: str
    repo: str
    message: str
    author: str = ""
    timestamp: datetime | None = None
    diff_summary: str = ""


class TicketData(BaseModel):
    """Normalised ticket data from Jira / Linear."""

    ticket_id: str
    title: str
    description: str = ""
    status: str = ""
    assignee: str = ""
    labels: list[str] = Field(default_factory=list)
    linked_prs: list[str] = Field(default_factory=list)
    timestamp: datetime | None = None


class SlackThread(BaseModel):
    """Normalised Slack thread."""

    thread_id: str
    channel: str
    messages: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    timestamp: datetime | None = None


# ---------------------------------------------------------------------------
# Retrieval / reasoning
# ---------------------------------------------------------------------------

class RetrievalPlan(BaseModel):
    """A plan produced by the context assembly engine."""

    question_type: QuestionType
    vector_queries: list[str] = Field(default_factory=list)
    graph_traversals: list[str] = Field(default_factory=list)
    keyword_filters: list[str] = Field(default_factory=list)
    source_type_filters: list[SourceType] = Field(default_factory=list)


class SourceCitation(BaseModel):
    """A citation pointing back to the original source."""

    source_type: SourceType
    source_id: str
    title: str = ""
    url: str = ""
    timestamp: datetime | None = None


class QueryResponse(BaseModel):
    """Final response returned to the user."""

    answer: str
    citations: list[SourceCitation] = Field(default_factory=list)
    confidence: float = 0.0
    staleness_warnings: list[str] = Field(default_factory=list)
    model_used: str = ""


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditEntry(BaseModel):
    """Immutable audit log entry."""

    user_id: str
    query: str
    response_summary: str = ""
    chunks_retrieved: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
