"""FastAPI application — REST + streaming interface layer.

Production-grade features:
- API key authentication (via middleware)
- Rate limiting (via middleware)
- Security headers (CSP, X-Frame-Options, etc.) via middleware
- Request logging with correlation IDs (via middleware)
- Thread-safe chunk repository
- Input validation with size limits
- Structured error responses
- Deep health checks
- Audit logging for compliance
- Feedback collection on answers
- Usage statistics and analytics
- Chunk browsing with pagination
- CSV audit export
"""

from __future__ import annotations

import csv
import io
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from src.config.settings import get_settings
from src.context_assembly.assembler import ContextAssembler, classify_question
from src.interfaces.middleware import (
    APIKeyMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from src.models.repository import ChunkRepository
from src.models.schemas import Chunk, QueryResponse, QuestionType
from src.reasoning.engine import ReasoningEngine, compute_confidence, extract_citations
from src.security.auth import AuditLogger, FeedbackStore, PermissionFilter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Enterprise Tool",
    description="Internal developer copilot with org-wide context, "
    "temporal awareness, and large context reasoning.",
    version="0.2.0",
)

# Middleware stack (order matters — outermost first)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production via config
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Shared state — thread-safe, dependency-injectable
# ---------------------------------------------------------------------------

_chunk_repo = ChunkRepository()
_audit_logger = AuditLogger()
_permission_filter = PermissionFilter()
_context_assembler = ContextAssembler()
_feedback_store = FeedbackStore()


def get_chunk_repository() -> ChunkRepository:
    """Return the application-wide chunk repository."""
    return _chunk_repo


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The question to answer")
    user_id: str = Field(default="anonymous", min_length=1, max_length=256)
    stream: bool = False
    user_permissions: list[str] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def _validate_query_length(cls, v: str) -> str:
        settings = get_settings()
        if len(v) > settings.max_query_length:
            raise ValueError(
                f"Query exceeds maximum length of {settings.max_query_length} characters"
            )
        return v


class IngestRequest(BaseModel):
    owner: str = Field(..., min_length=1, max_length=256, pattern=r"^[a-zA-Z0-9._-]+$")
    repo: str = Field(..., min_length=1, max_length=256, pattern=r"^[a-zA-Z0-9._-]+$")


class FeedbackRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    rating: str = Field(..., pattern=r"^(up|down)$")
    user_id: str = Field(default="anonymous", min_length=1, max_length=256)
    comment: str = Field(default="", max_length=2000)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.2.0"
    chunks_indexed: int = 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check with system status."""
    return HealthResponse(chunks_indexed=_chunk_repo.count)


@app.post("/ask", response_model=QueryResponse)
async def ask(req: AskRequest) -> Any:
    """Answer a developer question using assembled context."""
    try:
        question_type = classify_question(req.query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Permission-aware retrieval from thread-safe repository
    candidates = _permission_filter.filter(
        _chunk_repo.list_all(), set(req.user_permissions)
    )
    assembled = _context_assembler.assemble(req.query, candidates)

    if not assembled:
        return QueryResponse(
            answer="I don't have enough context to answer this question yet. "
            "Please ensure relevant data sources have been ingested.",
            confidence=0.0,
            model_used="none",
        )

    if req.stream:
        return _stream_response(req.query, assembled, question_type)

    engine = ReasoningEngine()
    try:
        response = await engine.answer(req.query, assembled, question_type)
    except Exception as exc:
        logger.exception("LLM call failed for query: %s", req.query[:100])
        raise HTTPException(
            status_code=502,
            detail="Failed to generate response from LLM. Please try again.",
        ) from exc

    _audit_logger.log(
        user_id=req.user_id,
        query=req.query,
        response_summary=response.answer[:200] if response.answer else "",
        chunks_retrieved=[c.metadata.source_id for c in assembled],
    )
    return response


def _stream_response(
    query: str, chunks: list[Chunk], question_type: QuestionType
) -> StreamingResponse:
    engine = ReasoningEngine()

    async def _generate():
        async for token in engine.answer_stream(query, chunks, question_type):
            yield token

    return StreamingResponse(_generate(), media_type="text/plain")


@app.post("/ingest/github")
async def ingest_github(req: IngestRequest) -> dict[str, Any]:
    """Trigger GitHub ingestion for a repository."""
    from src.ingestion.github_ingester import GitHubIngester
    from src.processing.chunker import SemanticChunker
    from src.processing.temporal_tagger import TemporalTagger

    settings = get_settings()
    if not settings.github_token:
        raise HTTPException(status_code=500, detail="GitHub token not configured")

    try:
        ingester = GitHubIngester(settings.github_token)
        data = await ingester.ingest_repository(req.owner, req.repo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("GitHub ingestion failed for %s/%s", req.owner, req.repo)
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API error: {exc}",
        ) from exc

    chunker = SemanticChunker()
    tagger = TemporalTagger()

    new_chunks: list[Chunk] = []
    for pr in data["pull_requests"]:
        for chunk in chunker.chunk_pr(pr):
            tagger.tag_chunk(chunk)
            new_chunks.append(chunk)
    for commit in data["commits"]:
        for chunk in chunker.chunk_commit(commit):
            tagger.tag_chunk(chunk)
            new_chunks.append(chunk)

    _chunk_repo.add_many(new_chunks)

    return {
        "status": "ok",
        "chunks_created": len(new_chunks),
        "prs_ingested": len(data["pull_requests"]),
        "commits_ingested": len(data["commits"]),
    }


@app.post("/webhook/github")
async def github_webhook(request: Request) -> dict[str, str]:
    """Handle GitHub webhook events (PR opened/updated)."""
    from src.ingestion.github_ingester import GitHubIngester
    from src.processing.chunker import SemanticChunker
    from src.processing.temporal_tagger import TemporalTagger
    from src.security.auth import verify_github_signature

    settings = get_settings()
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if settings.github_webhook_secret:
        if not verify_github_signature(body, sig, settings.github_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    event = request.headers.get("X-GitHub-Event", "")

    if event == "pull_request":
        pr = GitHubIngester.parse_webhook_pr(payload)
        if pr:
            chunker = SemanticChunker()
            tagger = TemporalTagger()
            for chunk in chunker.chunk_pr(pr):
                tagger.tag_chunk(chunk)
                _chunk_repo.add(chunk)

    return {"status": "ok"}


@app.get("/audit")
async def get_audit_log() -> list[dict[str, Any]]:
    """Return the audit trail."""
    return [e.model_dump(mode="json") for e in _audit_logger.entries]


@app.get("/audit/export")
async def export_audit_csv() -> StreamingResponse:
    """Export the audit trail as a CSV file."""
    entries = _audit_logger.entries
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "user_id", "query", "response_summary", "chunks_retrieved"])
    for e in entries:
        writer.writerow([
            e.timestamp.isoformat() if e.timestamp else "",
            e.user_id,
            e.query,
            e.response_summary,
            ";".join(e.chunks_retrieved),
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )


@app.post("/feedback")
async def submit_feedback(req: FeedbackRequest) -> dict[str, str]:
    """Submit thumbs-up/down feedback on an answer."""
    _feedback_store.add(
        user_id=req.user_id,
        query=req.query,
        rating=req.rating,
        comment=req.comment,
    )
    return {"status": "ok"}


@app.get("/feedback")
async def get_feedback() -> list[dict[str, Any]]:
    """Return all collected feedback entries."""
    return [e.model_dump(mode="json") for e in _feedback_store.entries]


@app.get("/chunks")
async def list_chunks(
    source_type: str | None = Query(None, description="Filter by source type"),
    repo: str | None = Query(None, description="Filter by repository"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
) -> dict[str, Any]:
    """Browse ingested chunks with pagination and filtering."""
    all_chunks = _chunk_repo.list_all()

    if source_type:
        all_chunks = [c for c in all_chunks if c.metadata.source_type.value == source_type]
    if repo:
        all_chunks = [c for c in all_chunks if c.metadata.repo == repo]

    total = len(all_chunks)
    start = (page - 1) * per_page
    end = start + per_page
    page_chunks = all_chunks[start:end]

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "chunks": [
            {
                "id": c.id,
                "source_type": c.metadata.source_type.value,
                "source_id": c.metadata.source_id,
                "repo": c.metadata.repo,
                "author": c.metadata.author,
                "timestamp": c.metadata.timestamp.isoformat() if c.metadata.timestamp else None,
                "staleness_score": c.staleness_score,
                "is_outdated": c.metadata.is_likely_outdated,
                "content_preview": c.content[:200] + ("…" if len(c.content) > 200 else ""),
            }
            for c in page_chunks
        ],
    }


@app.get("/stats")
async def get_stats() -> dict[str, Any]:
    """Return usage statistics and analytics."""
    all_chunks = _chunk_repo.list_all()
    audit_entries = _audit_logger.entries
    feedback_entries = _feedback_store.entries

    # Chunk stats
    source_counts: Counter[str] = Counter()
    repo_counts: Counter[str] = Counter()
    outdated_count = 0
    for c in all_chunks:
        source_counts[c.metadata.source_type.value] += 1
        if c.metadata.repo:
            repo_counts[c.metadata.repo] += 1
        if c.metadata.is_likely_outdated:
            outdated_count += 1

    # Feedback stats
    up_count = sum(1 for f in feedback_entries if f.rating == "up")
    down_count = sum(1 for f in feedback_entries if f.rating == "down")

    # Query stats
    user_counts: Counter[str] = Counter()
    for e in audit_entries:
        user_counts[e.user_id] += 1

    return {
        "chunks": {
            "total": len(all_chunks),
            "by_source_type": dict(source_counts),
            "by_repo": dict(repo_counts),
            "outdated": outdated_count,
        },
        "queries": {
            "total": len(audit_entries),
            "by_user": dict(user_counts.most_common(10)),
        },
        "feedback": {
            "total": len(feedback_entries),
            "positive": up_count,
            "negative": down_count,
            "satisfaction_rate": round(up_count / max(1, up_count + down_count), 2),
        },
    }


# ---------------------------------------------------------------------------
# Static files & Web UI
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).parent / "static"

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    """Serve the web UI."""
    index_path = _STATIC_DIR / "index.html"
    if index_path.is_file():
        return FileResponse(str(index_path))
    return JSONResponse({"message": "AI Enterprise Tool API", "docs": "/docs"})


# ---------------------------------------------------------------------------
# Global error handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."},
    )
