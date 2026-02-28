# AI Enterprise Tool

Production-grade internal developer copilot with org-wide context, temporal awareness, and large context reasoning.

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
| `GET` | `/health` | Health check |
| `POST` | `/ask` | Ask a question (supports streaming) |
| `POST` | `/ingest/github` | Ingest a GitHub repository |
| `POST` | `/webhook/github` | GitHub webhook receiver |
| `GET` | `/audit` | View audit log |

### Example: Ask a Question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Why does the payments service have its own user table?", "user_id": "alice"}'
```

## Docker

```bash
docker compose up --build
```

## Project Structure

```
src/
├── config/           # Application settings (env-based)
├── models/           # Pydantic schemas shared across layers
├── ingestion/        # Data source connectors (GitHub, Slack)
├── processing/       # Semantic chunking, temporal tagging
├── context_assembly/ # Query classification, retrieval planning, token budgeting
├── reasoning/        # LLM integration, citations, confidence scoring
├── interfaces/       # FastAPI REST API
└── security/         # Permission filtering, audit logging, webhook verification
tests/
├── unit/             # Unit tests for each layer
└── integration/      # Integration tests (requires services)
```

## Security

- **Permission filtering** — chunks carry source permissions; retrieval filters by user access
- **Audit logging** — every query, retrieval, and response is logged
- **Webhook verification** — GitHub and Slack signatures are validated
- **Data isolation** — designed for per-tenant Qdrant collections and Neo4j databases

## Tech Stack

- **Backend:** Python / FastAPI
- **LLM:** Anthropic Claude API
- **Vector Store:** Qdrant
- **Primary DB:** PostgreSQL (via SQLAlchemy + asyncpg)
- **Cache / Queue:** Redis
- **Deployment:** Docker + Docker Compose