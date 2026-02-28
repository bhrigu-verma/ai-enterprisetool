"""SQLAlchemy models for persistent storage.

These models back PostgreSQL tables for:
- Ingested chunks (metadata; content is also in Qdrant for vector search)
- Audit log entries
- Ingestion job tracking (idempotency)
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ChunkRow(Base):
    """Persistent chunk metadata (mirrors :class:`Chunk` in schemas)."""

    __tablename__ = "chunks"

    id = Column(String(64), primary_key=True)
    content = Column(Text, nullable=False)
    source_type = Column(String(32), nullable=False, index=True)
    source_id = Column(String(512), nullable=False, index=True)
    author = Column(String(256), nullable=False, default="")
    repo = Column(String(256), nullable=False, default="", index=True)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    age_days = Column(Integer, nullable=False, default=0)
    staleness_score = Column(Float, nullable=False, default=0.0)
    staleness_reason = Column(Text, nullable=False, default="")
    is_likely_outdated = Column(Boolean, nullable=False, default=False)
    tags = Column(ARRAY(String), nullable=False, default=[])
    linked_entities = Column(ARRAY(String), nullable=False, default=[])
    permissions = Column(ARRAY(String), nullable=False, default=[])
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_chunks_source_type_repo", "source_type", "repo"),
    )


class AuditRow(Base):
    """Persistent audit log entry."""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(256), nullable=False, index=True)
    query = Column(Text, nullable=False)
    response_summary = Column(Text, nullable=False, default="")
    chunks_retrieved = Column(ARRAY(String), nullable=False, default=[])
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class IngestionJob(Base):
    """Tracks ingestion runs for idempotency and progress monitoring."""

    __tablename__ = "ingestion_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(32), nullable=False)  # "github", "slack", etc.
    source_identifier = Column(String(512), nullable=False)  # "owner/repo"
    status = Column(String(32), nullable=False, default="pending", index=True)
    chunks_created = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_ingestion_source", "source", "source_identifier"),
    )
