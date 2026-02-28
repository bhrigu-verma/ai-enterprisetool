"""FastAPI application — REST + streaming interface layer."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.config.settings import get_settings
from src.context_assembly.assembler import ContextAssembler, classify_question
from src.models.schemas import Chunk, QueryResponse, QuestionType
from src.reasoning.engine import ReasoningEngine, _compute_confidence, _extract_citations
from src.security.auth import AuditLogger, PermissionFilter

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Enterprise Tool",
    description="Internal developer copilot with org-wide context",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Shared state (replaced by DI in production)
# ---------------------------------------------------------------------------

_audit_logger = AuditLogger()
_permission_filter = PermissionFilter()
_context_assembler = ContextAssembler()

# In-memory chunk store for the MVP — replaced by Qdrant in production.
_chunk_store: list[Chunk] = []


def get_chunk_store() -> list[Chunk]:
    return _chunk_store


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    query: str
    user_id: str = "anonymous"
    stream: bool = False
    user_permissions: list[str] = Field(default_factory=list)


class IngestRequest(BaseModel):
    owner: str
    repo: str


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@app.post("/ask", response_model=QueryResponse)
async def ask(req: AskRequest) -> Any:
    """Answer a developer question using assembled context."""
    question_type = classify_question(req.query)

    # Permission-aware retrieval
    candidates = _permission_filter.filter(
        _chunk_store, set(req.user_permissions)
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
        logger.exception("LLM call failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _audit_logger.log(
        user_id=req.user_id,
        query=req.query,
        response_summary=response.answer[:200],
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

    ingester = GitHubIngester(settings.github_token)
    data = await ingester.ingest_repository(req.owner, req.repo)

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

    _chunk_store.extend(new_chunks)

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

    if settings.github_webhook_secret and not verify_github_signature(
        body, sig, settings.github_webhook_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event = request.headers.get("X-GitHub-Event", "")

    if event == "pull_request":
        pr = GitHubIngester.parse_webhook_pr(payload)
        if pr:
            chunker = SemanticChunker()
            tagger = TemporalTagger()
            for chunk in chunker.chunk_pr(pr):
                tagger.tag_chunk(chunk)
                _chunk_store.append(chunk)

    return {"status": "ok"}


@app.get("/audit")
async def get_audit_log() -> list[dict[str, Any]]:
    """Return the audit trail."""
    return [e.model_dump(mode="json") for e in _audit_logger.entries]
