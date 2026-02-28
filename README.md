# AI Enterprise Tool

Production-grade internal developer copilot with org-wide context, temporal awareness, and large context reasoning.

![Web UI](https://github.com/user-attachments/assets/77aa6bb9-aeba-493d-b852-f4fed0f7a40b)

> **📖 Full documentation:** [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md)

## What It Does

An internal engineering assistant that understands the **entire engineering org** — not just code, but decisions, history, context, and reasoning. A developer asks it anything and gets an answer grounded in *how the company actually works*.

**Three differentiators:**
1. **Org-wide context** — repos, PRs, tickets, Slack threads, and docs — all unified
2. **Temporal awareness** — knows that a decision from 2 years ago may be outdated
3. **Large context reasoning** — loads full documents, not snippets

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   INGESTION LAYER                   │
│  GitHub → PR / Commit Ingester                      │
│  Slack  → Thread Ingester                           │
│  (Jira / Linear / Confluence — planned)             │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│               PROCESSING LAYER                      │
│  Semantic Chunker (by function/section/thread)      │
│  Temporal Tagger (staleness scoring)                │
│  Metadata Extractor + Entity Linker                 │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              CONTEXT ASSEMBLY ENGINE                │
│  Query Classifier (why / how / who / incident)      │
│  Retrieval Planner (source type routing)            │
│  Token Budget Manager                               │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                 REASONING LAYER                     │
│  Claude API (Opus for complex, Sonnet for fast)     │
│  Source Citation Builder                            │
│  Confidence Scorer                                  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│               INTERFACE LAYER                       │
│  FastAPI REST + Streaming API                       │
│  GitHub Webhook Receiver                            │
│  (Slack Bot — planned)                              │
└─────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Configure (copy and edit .env)
cp .env.example .env  # set your API keys

# Run the server
uvicorn src.interfaces.api:app --reload

# Run tests
pytest tests/
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check with chunk count |
| `POST` | `/ask` | Ask a question (supports streaming) |
| `POST` | `/ingest/github` | Ingest a GitHub repository |
| `POST` | `/webhook/github` | GitHub webhook receiver |
| `GET` | `/chunks` | Browse knowledge base (paginated, filterable) |
| `GET` | `/stats` | Usage analytics and satisfaction metrics |
| `POST` | `/feedback` | Submit thumbs-up/down feedback |
| `GET` | `/feedback` | Retrieve all feedback entries |
| `GET` | `/audit` | View audit log |
| `GET` | `/audit/export` | Export audit log as CSV |
| `GET` | `/` | Web UI |

### Example: Ask a Question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"query": "Why does the payments service have its own user table?", "user_id": "alice"}'
```

## Docker

```bash
docker compose up --build
```

## Project Structure

```
src/
├── config/           # Settings (env-based) + resilience utilities (retry, backoff)
├── models/           # Pydantic schemas, SQLAlchemy models, thread-safe repository
├── ingestion/        # Data source connectors (GitHub, Slack) with retry + pagination
├── processing/       # Semantic chunking, temporal tagging, entity linker
├── context_assembly/ # Query classification, retrieval planning, token budgeting
├── reasoning/        # LLM integration, citations, confidence scoring
├── interfaces/       # FastAPI REST API + Web UI (6 views) + middleware (auth, rate limit, security headers)
└── security/         # Permission filtering, audit logging, feedback, webhook verification
tests/
├── unit/             # 131 unit tests covering all layers
└── integration/      # Integration tests (requires services)
docs/
└── DOCUMENTATION.md  # Comprehensive documentation
```

## Security

- **Security headers** — Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy
- **API key authentication** — configurable API keys via middleware; public endpoints (health, docs) skip auth
- **Rate limiting** — per-IP sliding window rate limiter
- **Permission filtering** — chunks carry source permissions; retrieval filters by user access
- **Audit logging** — every query, retrieval, and response is logged with timestamps; CSV export available
- **Webhook verification** — GitHub (HMAC-SHA256) and Slack (with replay protection) signatures validated
- **Input validation** — size limits, format validation, and Pydantic constraints at all boundaries
- **Request logging** — correlation IDs for distributed tracing
- **Data isolation** — designed for per-tenant Qdrant collections and Neo4j databases

## Tech Stack

- **Backend:** Python / FastAPI
- **LLM:** Anthropic Claude API
- **Vector Store:** Qdrant
- **Primary DB:** PostgreSQL (via SQLAlchemy + asyncpg)
- **Cache / Queue:** Redis
- **Deployment:** Docker + Docker Compose