# AI Enterprise Tool — Comprehensive Documentation

> **Version 0.2.0** · Internal Developer Copilot with Org-Wide Context, Temporal Awareness, and Large Context Reasoning

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Getting Started](#3-getting-started)
4. [Configuration Reference](#4-configuration-reference)
5. [API Reference](#5-api-reference)
6. [Web UI Guide](#6-web-ui-guide)
7. [Ingestion Pipeline](#7-ingestion-pipeline)
8. [Processing Layer](#8-processing-layer)
9. [Context Assembly Engine](#9-context-assembly-engine)
10. [Reasoning Layer](#10-reasoning-layer)
11. [Security & Compliance](#11-security--compliance)
12. [Deployment](#12-deployment)
13. [Testing](#13-testing)
14. [Project Structure](#14-project-structure)
15. [Troubleshooting](#15-troubleshooting)
16. [Changelog](#16-changelog)

---

## 1. Overview

The AI Enterprise Tool is a production-grade internal engineering assistant that understands your **entire engineering organization** — not just code, but decisions, history, context, and reasoning. A developer asks it anything and gets an answer grounded in how the company actually works.

### Three Differentiators

| Capability | Description |
|---|---|
| **Org-wide context** | Unifies repositories, PRs, tickets, Slack threads, and documentation |
| **Temporal awareness** | Knows that a decision from 2 years ago may be outdated; scores content freshness |
| **Large context reasoning** | Loads full documents into the LLM context, not isolated snippets |

### Key Features (v0.2.0)

- **Ask anything** — natural language questions about architecture, incidents, ownership, and more
- **Source citations** — every answer links back to the specific PR, ticket, Slack thread, or doc
- **Staleness detection** — content flagged as potentially outdated with reasons
- **Real-time streaming** — token-by-token streamed responses for immediate feedback
- **Feedback collection** — thumbs up/down on answers to track satisfaction
- **Analytics dashboard** — usage metrics, satisfaction rate, knowledge base health
- **Knowledge base browser** — paginated, filterable view of all ingested content
- **Audit logging** — every query and retrieval logged with timestamps for compliance
- **Security hardening** — CSP, API key auth, rate limiting, permission filtering, webhook signature verification

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────┐
│                   INGESTION LAYER                   │
│  GitHub → PR / Commit Ingester (with pagination)    │
│  Slack  → Thread Ingester (with retry/backoff)      │
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
│  Token Budget Manager (greedy fit)                  │
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
│  Web UI (6 views, dark/light theme)                 │
│  GitHub Webhook Receiver                            │
│  Security Middleware Stack                          │
│  (Slack Bot — planned)                              │
└─────────────────────────────────────────────────────┘
```

### Data Flow

1. **Ingestion** — Data is pulled from GitHub (PRs, commits) or Slack (threads) via authenticated API calls with automatic pagination and retry logic.
2. **Processing** — Raw data is broken into semantically meaningful chunks, tagged with temporal staleness scores, and enriched with entity links (PR ↔ ticket ↔ Slack thread).
3. **Storage** — Chunks are stored in the thread-safe in-memory repository (development) or PostgreSQL + Qdrant (production).
4. **Query** — A user's natural language question is classified by type (why/how/who/incident), a retrieval plan targets the right source types, candidates are ranked by freshness and fitted into the LLM's token budget.
5. **Reasoning** — The assembled context and question are sent to Claude. The response includes source citations and staleness warnings.
6. **Response** — The answer is returned via REST (JSON) or streamed token-by-token, with audit logging.

---

## 3. Getting Started

### Prerequisites

- Python 3.11+
- An Anthropic API key (for Claude LLM)
- A GitHub personal access token (for repository ingestion)

### Installation

```bash
# Clone the repository
git clone https://github.com/bhrigu-verma/ai-enterprisetool.git
cd ai-enterprisetool

# Install with development dependencies
pip install -e ".[dev]"

# Copy and configure environment
cp .env.example .env
# Edit .env and set your API keys
```

### Run the Server

```bash
# Development (with auto-reload)
uvicorn src.interfaces.api:app --reload

# Production
uvicorn src.interfaces.api:app --host 0.0.0.0 --port 8000 --workers 4
```

The web UI is available at `http://localhost:8000/` and the API docs at `http://localhost:8000/docs`.

### Run Tests

```bash
# All tests
pytest tests/

# With coverage
pytest tests/ --cov=src --cov-report=html

# Just unit tests
pytest tests/unit/ -v
```

### Docker

```bash
# Build and start all services (app + Redis + Qdrant)
docker compose up --build

# The app will be available at http://localhost:8000
```

---

## 4. Configuration Reference

All settings are loaded from environment variables prefixed with `AET_`. A `.env` file is supported.

### Application

| Variable | Default | Description |
|---|---|---|
| `AET_APP_NAME` | `AI Enterprise Tool` | Application display name |
| `AET_COMPANY_NAME` | `Acme Corp` | Company name used in LLM system prompt |
| `AET_DEBUG` | `false` | Enable debug mode |

### API Authentication

| Variable | Default | Description |
|---|---|---|
| `AET_API_KEYS` | `[]` | JSON array of valid API keys. When empty, authentication is disabled (dev mode). |

Generate a secure key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Anthropic (LLM)

| Variable | Default | Description |
|---|---|---|
| `AET_ANTHROPIC_API_KEY` | *(required)* | Anthropic API key for Claude |
| `AET_OPUS_MODEL` | `claude-sonnet-4-20250514` | Model for complex questions (why, who, incidents) |
| `AET_SONNET_MODEL` | `claude-sonnet-4-20250514` | Model for simpler questions (how, factual, general) |
| `AET_MAX_CONTEXT_TOKENS` | `150000` | Maximum tokens in LLM context window |
| `AET_LLM_MAX_OUTPUT_TOKENS` | `4096` | Maximum output tokens per response |
| `AET_LLM_TIMEOUT_SECONDS` | `120` | Timeout for LLM API calls |

### GitHub

| Variable | Default | Description |
|---|---|---|
| `AET_GITHUB_TOKEN` | *(required for ingestion)* | GitHub personal access token |
| `AET_GITHUB_WEBHOOK_SECRET` | *(optional)* | Secret for verifying webhook signatures |

### Slack

| Variable | Default | Description |
|---|---|---|
| `AET_SLACK_BOT_TOKEN` | *(optional)* | Slack bot OAuth token |
| `AET_SLACK_SIGNING_SECRET` | *(optional)* | Slack signing secret for request verification |
| `AET_SLACK_INDEXED_CHANNELS` | `[]` | JSON array of Slack channel IDs to index |

### Infrastructure

| Variable | Default | Description |
|---|---|---|
| `AET_QDRANT_URL` | `http://localhost:6333` | Qdrant vector store URL |
| `AET_QDRANT_API_KEY` | *(optional)* | Qdrant API key |
| `AET_QDRANT_COLLECTION` | `enterprise_knowledge` | Qdrant collection name |
| `AET_DATABASE_URL` | `postgresql+asyncpg://localhost:5432/aet` | PostgreSQL connection string |
| `AET_REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |

### Embedding

| Variable | Default | Description |
|---|---|---|
| `AET_EMBEDDING_MODEL` | `text-embedding-3-large` | OpenAI embedding model |
| `AET_EMBEDDING_DIMENSION` | `3072` | Embedding vector dimension |
| `AET_OPENAI_API_KEY` | *(optional)* | OpenAI API key for embeddings |

### Tuning

| Variable | Default | Description |
|---|---|---|
| `AET_STALENESS_THRESHOLD_DAYS` | `540` | Days after which content is considered potentially stale |
| `AET_RATE_LIMIT_PER_MINUTE` | `60` | Maximum requests per IP per minute |
| `AET_RATE_LIMIT_BURST` | `10` | Burst rate limit |
| `AET_CORS_ALLOWED_ORIGINS` | `["*"]` | JSON array of allowed CORS origins. Restrict in production. |
| `AET_MAX_QUERY_LENGTH` | `10000` | Maximum characters per query |
| `AET_MAX_INGEST_BATCH_SIZE` | `100` | Maximum items per ingestion batch |

---

## 5. API Reference

Base URL: `http://localhost:8000`

### Health Check

```
GET /health
```

Returns system status and indexed chunk count.

**Response:**
```json
{
  "status": "ok",
  "version": "0.2.0",
  "chunks_indexed": 42
}
```

---

### Ask a Question

```
POST /ask
```

Submit a natural-language question. Supports both complete and streamed responses.

**Request Body:**
```json
{
  "query": "Why does the payments service have its own user table?",
  "user_id": "alice",
  "stream": false,
  "user_permissions": ["repo:backend", "repo:payments"]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | string | Yes | The question (1–10,000 characters) |
| `user_id` | string | No | User identifier for audit (default: `anonymous`) |
| `stream` | boolean | No | Stream response token-by-token (default: `false`) |
| `user_permissions` | string[] | No | Permission strings for content filtering |

**Response (non-streaming):**
```json
{
  "answer": "The payments service has its own user table because...",
  "citations": [
    {
      "source_type": "pr_description",
      "source_id": "PR-142",
      "title": "",
      "url": "",
      "timestamp": "2024-03-15T10:30:00Z"
    }
  ],
  "confidence": 0.85,
  "staleness_warnings": [],
  "model_used": "claude-sonnet-4-20250514"
}
```

**Response (streaming):** Returns `text/plain` with tokens streamed as they are generated.

---

### Ingest GitHub Repository

```
POST /ingest/github
```

Trigger ingestion of PRs and commits from a GitHub repository.

**Request Body:**
```json
{
  "owner": "acme",
  "repo": "backend"
}
```

**Response:**
```json
{
  "status": "ok",
  "chunks_created": 156,
  "prs_ingested": 45,
  "commits_ingested": 200
}
```

---

### GitHub Webhook

```
POST /webhook/github
```

Receives GitHub webhook events. Processes `pull_request` events to ingest PR data in real-time.

**Headers:**
- `X-GitHub-Event`: Event type (e.g., `pull_request`)
- `X-Hub-Signature-256`: HMAC-SHA256 signature (when webhook secret is configured)

---

### Browse Knowledge Base

```
GET /chunks?source_type=pr_description&repo=acme/backend&page=1&per_page=20
```

Browse ingested chunks with pagination and filtering.

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `source_type` | string | Filter by source type (`pr_description`, `pr_comment`, `commit`, `slack_thread`, `ticket`, `document`, `code`) |
| `repo` | string | Filter by repository name |
| `page` | integer | Page number (default: 1) |
| `per_page` | integer | Items per page (1–100, default: 20) |

**Response:**
```json
{
  "total": 156,
  "page": 1,
  "per_page": 20,
  "pages": 8,
  "chunks": [
    {
      "id": "abc123",
      "source_type": "pr_description",
      "source_id": "PR-142",
      "repo": "acme/backend",
      "author": "alice",
      "timestamp": "2024-03-15T10:30:00Z",
      "staleness_score": 0.12,
      "is_outdated": false,
      "content_preview": "PR #142: Add payments isolation layer..."
    }
  ]
}
```

---

### Usage Statistics

```
GET /stats
```

Returns analytics on usage, satisfaction, and knowledge base health.

**Response:**
```json
{
  "chunks": {
    "total": 156,
    "by_source_type": {
      "pr_description": 45,
      "commit": 100,
      "pr_comment": 11
    },
    "by_repo": {
      "acme/backend": 80,
      "acme/frontend": 76
    },
    "outdated": 3
  },
  "queries": {
    "total": 250,
    "by_user": {
      "alice": 45,
      "bob": 32
    }
  },
  "feedback": {
    "total": 100,
    "positive": 82,
    "negative": 18,
    "satisfaction_rate": 0.82
  }
}
```

---

### Submit Feedback

```
POST /feedback
```

Submit thumbs-up/down feedback on an answer.

**Request Body:**
```json
{
  "query": "Why does payments have its own user table?",
  "rating": "up",
  "user_id": "alice",
  "comment": "Very helpful with the right context!"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | string | Yes | The original question (1–10,000 characters) |
| `rating` | string | Yes | `"up"` or `"down"` |
| `user_id` | string | No | User identifier (default: `anonymous`) |
| `comment` | string | No | Optional text comment (max 2,000 characters) |

---

### Get Feedback

```
GET /feedback
```

Returns all collected feedback entries.

**Response:**
```json
[
  {
    "user_id": "alice",
    "query": "Why does payments have its own user table?",
    "rating": "up",
    "comment": "Very helpful!",
    "timestamp": "2024-03-15T12:00:00Z"
  }
]
```

---

### Audit Log

```
GET /audit
```

Returns the full audit trail of queries and retrievals.

**Response:**
```json
[
  {
    "user_id": "alice",
    "query": "Why does payments have its own user table?",
    "response_summary": "The payments service has its own user table because...",
    "chunks_retrieved": ["PR-142", "TICKET-ENG-100"],
    "timestamp": "2024-03-15T12:00:00Z"
  }
]
```

---

### Export Audit Log as CSV

```
GET /audit/export
```

Downloads the full audit log as a CSV file.

**Response:** `text/csv` file with columns: `timestamp`, `user_id`, `query`, `response_summary`, `chunks_retrieved`.

---

## 6. Web UI Guide

The web UI is served at the root path (`/`) and provides six views:

### Ask View

The primary interface. Type a question and get an answer with source citations, confidence scores, and staleness warnings.

**Features:**
- **Example queries** — click a suggested question to auto-fill the input
- **Streaming toggle** — enable/disable real-time token streaming
- **Feedback buttons** — thumbs up/down on each answer to track quality
- **Chat history** — all questions and answers are displayed in conversation format
- **Clear chat** — trash can icon resets the conversation
- **Markdown rendering** — responses render code blocks, bold, headings, and lists

### Ingest Data View

Connect external data sources. Currently supports GitHub repository ingestion.

**How to use:**
1. Enter the repository owner and name (e.g., `acme` / `backend`)
2. Click "Start Ingestion"
3. Wait for completion — the UI shows how many PRs, commits, and chunks were created

### Knowledge Base View

Browse and search all ingested content chunks.

**Features:**
- **Source type filter** — dropdown to show only PRs, commits, Slack threads, etc.
- **Repository filter** — text input to filter by repo name
- **Pagination** — navigate through large result sets
- **Content preview** — first 200 characters of each chunk displayed
- **Metadata** — source type badge, repo name, timestamp, chunk ID

### Analytics Dashboard

Monitor usage metrics, satisfaction rate, and knowledge base health.

**Displayed metrics:**
- Total chunks indexed
- Total queries processed
- Satisfaction rate (based on feedback)
- Number of outdated chunks
- Breakdown by source type, repository, and top querying users
- Feedback summary (positive, negative, total)

### Audit Log View

View all queries and retrievals for compliance.

**Features:**
- **Search/filter** — filter rows by search text
- **CSV export** — download the full audit log as CSV
- **Table columns** — timestamp, user ID, query text, chunks retrieved count

### System Status View

Monitor health of all system components.

**Status cards:**
- API Server — online/offline with version number
- Knowledge Base — active/empty with chunk count
- LLM Connection — configuration status
- GitHub Integration — webhook receiver status

### Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+K` | Focus the search/ask input |
| `?` | Show the keyboard shortcuts panel |
| `Escape` | Close modals |
| `1`–`6` | Switch views (when not typing in an input) |
| `Enter` | Send message |
| `Shift+Enter` | New line in input |

### Theme Toggle

Click the sun/moon icon in the sidebar footer to switch between **dark mode** and **light mode**. The preference is persisted in `localStorage`.

### Mobile Support

On screens narrower than 768px, the sidebar collapses and can be toggled with the hamburger menu button. Tapping outside the sidebar closes it automatically.

---

## 7. Ingestion Pipeline

### GitHub Ingester

**Module:** `src/ingestion/github_ingester.py`

Fetches and normalizes data from GitHub repositories via the REST API.

**Capabilities:**
- Automatic pagination (follows all pages up to a configurable maximum)
- Rate-limit awareness (reads `X-RateLimit` headers, backs off on 429)
- Retry with exponential backoff on transient errors (429, 500, 502, 503, 504)
- Input validation on owner/repo names
- Webhook payload parsing for real-time ingestion

**Data extracted:**
- **Pull Requests:** number, title, description, author, merged_by, review comments, linked issues, timestamp
- **Commits:** SHA, message, author, timestamp, diff summary

### Slack Ingester

**Module:** `src/ingestion/slack_ingester.py`

Fetches and normalizes Slack threads from indexed channels.

**Capabilities:**
- Conversations history and replies API
- Retry with exponential backoff
- Thread-level grouping (all replies kept together)
- Participant extraction

**Data extracted:**
- **Threads:** thread_id, channel, messages, participants, timestamp

---

## 8. Processing Layer

### Semantic Chunker

**Module:** `src/processing/chunker.py`

Splits content by meaningful boundaries — not by character count.

**Chunking rules:**

| Source | Strategy |
|---|---|
| PRs | Title + description as one chunk; each review comment as a separate chunk |
| Commits | One chunk per commit (message + optional diff summary) |
| Slack threads | Entire thread as one chunk (never split threads) |
| Tickets | Whole ticket as one chunk |
| Documents | Split by H2/H3 headings |

**Safety:**
- Maximum chunk size: 500,000 characters (configurable)
- Content exceeding the limit is truncated with a `[...truncated]` marker

### Temporal Tagger

**Module:** `src/processing/temporal_tagger.py`

Computes staleness scores for chunks based on three signals:

| Signal | Weight | Description |
|---|---|---|
| **Age** | 40% | How old is the content relative to the staleness threshold? |
| **File churn** | 35% | How many times have the referenced files changed since creation? |
| **Supersession** | 25% | Is there newer content that explicitly replaces this? |

**Staleness score range:** 0.0 (fresh) → 1.0 (very stale)

Chunks with a score ≥ 0.6 are flagged as `is_likely_outdated` and receive a human-readable reason.

### Entity Linker

**Module:** `src/processing/entity_linker.py`

Resolves cross-references between PRs, tickets, commits, and Slack threads.

**Extraction patterns:**
- GitHub PR references: `#123`
- Jira/Linear ticket IDs: `ENG-456`
- Commit SHAs: `abc1234` (7–40 hex characters)
- Slack channel links: `<#C123ABC|channel-name>`

**Fuzzy matching:**
- Finds entities whose title fuzzy-matches a query
- Uses a combination of SequenceMatcher and token-overlap (Jaccard-like) scoring
- Configurable threshold (default: 0.3)

---

## 9. Context Assembly Engine

**Module:** `src/context_assembly/assembler.py`

This is the core of the product. The naive approach (embed query → top-K chunks → stuff into context) fails for complex questions. Instead:

### Step 1: Question Classification

Classifies queries into types using regex patterns:

| Type | Trigger words |
|---|---|
| `why` | why, reason, rationale, decision, chose, decided |
| `how` | how, implement, setup, configure, build, deploy |
| `who` | who, owner, maintainer, expert, knows, responsible |
| `what_broke` | broke, incident, outage, down, error, failure, bug |
| `general` | (default fallback) |

### Step 2: Retrieval Planning

Each question type targets specific source types:

| Question Type | Priority Sources |
|---|---|
| `why` | PR descriptions, tickets, Slack threads, documents |
| `how` | Code, documents, PR descriptions, commits |
| `who` | PR descriptions, commits, Slack threads |
| `what_broke` | Slack threads, PR descriptions, tickets |
| `general` | All source types |

### Step 3: Ranking

Chunks are sorted by a heuristic: lower staleness score + fewer age days = more relevant.

### Step 4: Token Budget

Chunks are greedily added until the token budget (default: 150,000) is exhausted. Token counting uses `tiktoken` with the `cl100k_base` encoding for accuracy.

---

## 10. Reasoning Layer

**Module:** `src/reasoning/engine.py`

### Model Routing

| Query Complexity | Model |
|---|---|
| Complex (why, who, incidents) | Opus model |
| Simple (how, factual, general) | Sonnet model |

### Response Structure

Every response includes:
- **Answer text** — the LLM's response
- **Source citations** — deduplicated list of source references
- **Confidence score** — heuristic based on chunk freshness and source diversity
- **Staleness warnings** — list of potentially outdated sources used
- **Model used** — which Claude model generated the response

### Confidence Scoring

```
confidence = min(1.0, (1.0 - avg_staleness) × 0.7 + source_diversity × 0.3)
```

Where:
- `avg_staleness` = average staleness score of assembled chunks
- `source_diversity` = number of distinct source types / total source types

### Streaming

The engine supports token-by-token streaming via `answer_stream()`. Mid-stream errors are logged and the stream ends with a user-friendly error message.

---

## 11. Security & Compliance

### Security Headers (v0.2.0)

Every response includes hardened security headers:

| Header | Value | Purpose |
|---|---|---|
| `Content-Security-Policy` | `default-src 'self'; script-src 'self' 'unsafe-inline'; ...` | Prevents XSS, data injection |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME type sniffing |
| `X-Frame-Options` | `DENY` | Prevents clickjacking |
| `X-XSS-Protection` | `1; mode=block` | Legacy XSS filter |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Controls referrer information |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Disables unnecessary browser APIs |

### API Key Authentication

- Configured via `AET_API_KEYS` (JSON array of strings)
- Sent via `X-API-Key` header
- When no keys are configured, authentication is disabled (development mode)
- Public endpoints (`/health`, `/docs`, `/openapi.json`, `/redoc`, `/`) skip authentication
- Webhook endpoints authenticate via signature, not API key
- Static file paths skip authentication

### Rate Limiting

- Per-IP sliding window rate limiter
- Default: 60 requests per minute per IP
- Returns HTTP 429 with `"Rate limit exceeded"` message when exceeded
- Thread-safe implementation with pruning of expired entries

### Permission Filtering

- Chunks carry source permissions (e.g., repo names, channel IDs)
- Retrieval filters chunks based on the requesting user's permission set
- Chunks with no permission constraints are accessible to everyone
- Chunks with permissions require at least one matching entry

### Audit Logging

- Every query and retrieval is logged with:
  - User ID
  - Query text
  - Response summary (first 200 characters)
  - List of retrieved chunk source IDs
  - Timestamp (UTC)
- Append-only store (in-memory for development, PostgreSQL for production)
- Exportable as CSV via `GET /audit/export`

### Webhook Verification

- **GitHub:** HMAC-SHA256 signature verification with constant-time comparison
- **Slack:** Signature verification with replay protection (rejects requests older than 5 minutes)

### Input Validation

- All request bodies validated with Pydantic v2 strict models
- Query length limited to 10,000 characters
- Owner/repo names validated against `^[a-zA-Z0-9._-]+$` pattern
- Feedback ratings restricted to `"up"` or `"down"`
- Chunk content truncated at 500,000 characters

### Request Logging

- Every request gets a unique correlation ID (via `X-Correlation-ID` header)
- Logs include method, path, status code, and duration in milliseconds
- Correlation IDs are returned in response headers for tracing

---

## 12. Deployment

### Docker Compose (Recommended)

```bash
docker compose up --build
```

This starts:
- **App** — FastAPI server on port 8000
- **Redis** — Cache/queue on port 6379
- **Qdrant** — Vector store on port 6333

### Manual Deployment

```bash
# Install
pip install -e .

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run with multiple workers
uvicorn src.interfaces.api:app --host 0.0.0.0 --port 8000 --workers 4
```

### Environment Variables

See [Configuration Reference](#4-configuration-reference) for all available settings.

### Health Check

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.2.0","chunks_indexed":0}
```

---

## 13. Testing

### Test Suite

The project includes 131 unit tests covering all layers:

```bash
# Run all tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=term-missing

# Run specific test modules
pytest tests/unit/test_api.py -v          # API endpoints (24 tests)
pytest tests/unit/test_security.py -v      # Security (18 tests)
pytest tests/unit/test_middleware.py -v     # Middleware (11 tests)
pytest tests/unit/test_chunker.py -v       # Chunking (8 tests)
pytest tests/unit/test_context_assembly.py -v  # Context assembly (10 tests)
pytest tests/unit/test_reasoning.py -v     # Reasoning (8 tests)
pytest tests/unit/test_repository.py -v    # Repository (10 tests)
pytest tests/unit/test_resilience.py -v    # Resilience (6 tests)
pytest tests/unit/test_entity_linker.py -v # Entity linker (9 tests)
pytest tests/unit/test_github_ingester.py -v  # GitHub ingester (5 tests)
pytest tests/unit/test_temporal_tagger.py -v  # Temporal tagger (6 tests)
pytest tests/unit/test_settings.py -v      # Settings (5 tests)
```

### Test Coverage by Feature

| Feature | Tests | Description |
|---|---|---|
| API endpoints | 24 | Health, ask, ingest, webhook, audit, feedback, chunks, stats, security headers |
| Security | 18 | Permission filtering, audit logging, feedback store, GitHub/Slack webhook verification |
| Middleware | 11 | API key auth, security headers (CSP, X-Frame-Options, etc.), static file auth bypass |
| Chunking | 8 | PR, commit, Slack, ticket, document chunking |
| Context assembly | 10 | Question classification, retrieval planning, token budgeting |
| Reasoning | 8 | Model selection, context formatting, citations, confidence scoring |
| Repository | 10 | CRUD, filtering, thread safety |
| Resilience | 6 | Retry logic, retryable status codes |
| Entity linker | 9 | Reference extraction, bidirectional linking, fuzzy matching |
| Temporal tagger | 6 | Staleness scoring, chunk tagging |
| Settings | 5 | Validation, defaults |

### Linting

```bash
# Run ruff linter
ruff check src/ tests/

# Run type checking
mypy src/
```

---

## 14. Project Structure

```
ai-enterprisetool/
├── src/
│   ├── config/
│   │   ├── settings.py          # Environment-based configuration (Pydantic Settings)
│   │   └── resilience.py        # Retry with exponential backoff + jitter
│   │
│   ├── models/
│   │   ├── schemas.py           # Pydantic domain models (Chunk, PRData, QueryResponse, etc.)
│   │   ├── repository.py        # Thread-safe in-memory chunk repository
│   │   └── database.py          # SQLAlchemy models (ChunkRow, AuditRow, IngestionJob)
│   │
│   ├── ingestion/
│   │   ├── github_ingester.py   # GitHub API client (PRs, commits, webhooks)
│   │   └── slack_ingester.py    # Slack API client (threads, replies)
│   │
│   ├── processing/
│   │   ├── chunker.py           # Semantic chunking by content type
│   │   ├── temporal_tagger.py   # Staleness scoring (age, churn, supersession)
│   │   └── entity_linker.py     # Cross-reference resolution + fuzzy matching
│   │
│   ├── context_assembly/
│   │   └── assembler.py         # Query classification, retrieval planning, token budgeting
│   │
│   ├── reasoning/
│   │   └── engine.py            # LLM integration (Claude), citations, confidence scoring
│   │
│   ├── interfaces/
│   │   ├── api.py               # FastAPI application (REST + streaming endpoints)
│   │   ├── middleware.py         # Auth, rate limiting, security headers, request logging
│   │   └── static/
│   │       ├── index.html       # Web UI (6 views, responsive layout)
│   │       ├── styles.css       # Design system (dark/light themes, 1600+ lines)
│   │       └── app.js           # Client-side logic (700 lines)
│   │
│   └── security/
│       └── auth.py              # Permissions, audit logging, feedback, webhook verification
│
├── tests/
│   ├── unit/                    # 131 unit tests
│   │   ├── test_api.py          # API endpoint tests
│   │   ├── test_middleware.py   # Middleware tests
│   │   ├── test_security.py     # Security tests
│   │   ├── test_chunker.py      # Chunking tests
│   │   ├── test_context_assembly.py  # Context assembly tests
│   │   ├── test_reasoning.py    # Reasoning tests
│   │   ├── test_repository.py   # Repository tests
│   │   ├── test_resilience.py   # Resilience tests
│   │   ├── test_entity_linker.py    # Entity linker tests
│   │   ├── test_github_ingester.py  # GitHub ingester tests
│   │   ├── test_temporal_tagger.py  # Temporal tagger tests
│   │   └── test_settings.py    # Settings tests
│   └── integration/            # Integration tests (require running services)
│
├── docs/
│   └── DOCUMENTATION.md        # This file
│
├── .env.example                # Environment configuration template
├── Dockerfile                  # Container image
├── docker-compose.yml          # Multi-service orchestration
├── pyproject.toml              # Python project configuration
└── README.md                   # Quick start guide
```

---

## 15. Troubleshooting

### Common Issues

**Q: The server starts but I get "Anthropic API key is not configured" on `/ask`**

Set `AET_ANTHROPIC_API_KEY` in your `.env` file. You need a valid Anthropic API key.

**Q: GitHub ingestion fails with "GitHub token not configured"**

Set `AET_GITHUB_TOKEN` in your `.env` file. Create a personal access token at https://github.com/settings/tokens with `repo` scope.

**Q: I get "Rate limit exceeded" errors**

The default rate limit is 60 requests per minute per IP. You can increase it by setting `AET_RATE_LIMIT_PER_MINUTE` in your `.env` file.

**Q: All my requests return 401 "Invalid or missing API key"**

You've configured `AET_API_KEYS` but aren't sending the key in requests. Either:
- Add `X-API-Key: your-key` header to requests, or
- Clear `AET_API_KEYS` to disable auth (development only)

**Q: The web UI shows "System Offline"**

The UI couldn't reach the `/health` endpoint. Check:
- Is the server running?
- Is it on the expected port?
- Are there CORS issues? (Set `AET_CORS_ALLOWED_ORIGINS` to include your frontend origin)

**Q: Chunks are marked as "likely outdated" but the content is current**

The staleness tagger uses age as the primary signal. You can:
- Increase `AET_STALENESS_THRESHOLD_DAYS` (default: 540 days)
- Re-ingest the data source to refresh timestamps

**Q: Token budget warning "Assembled 0 chunks using 0 tokens"**

No chunks matched the query's source type filters. Either:
- Ingest more data sources
- The query type classification may not match available content

---

## 16. Changelog

### v0.2.0 (Current)

**New Features:**
- Feedback collection endpoint (`POST /feedback`, `GET /feedback`) with thumbs up/down + optional comments
- Knowledge base browser (`GET /chunks`) with pagination and source type/repo filtering
- Usage analytics endpoint (`GET /stats`) with chunk counts, query stats, and satisfaction rate
- Audit log CSV export (`GET /audit/export`)
- 6-view web UI: Ask, Ingest, Knowledge Base, Analytics, Audit Log, System Status
- Dark/light theme toggle with `localStorage` persistence
- Keyboard shortcuts: `Ctrl+K` (focus search), `?` (help), `1`–`6` (view switch), `Escape` (close modals)
- Toast notification system for success/error/warning/info feedback
- Feedback buttons (thumbs up/down) on every assistant response
- Chat clear button
- Audit log search/filter + CSV export in the UI
- Mobile-responsive design with hamburger menu sidebar
- Improved markdown rendering (code blocks, bold, headings, bullet lists)
- Skeleton loading animations

**Security:**
- Content Security Policy (CSP) header
- `X-Frame-Options: DENY` header
- `X-Content-Type-Options: nosniff` header
- `X-XSS-Protection: 1; mode=block` header
- `Referrer-Policy: strict-origin-when-cross-origin` header
- `Permissions-Policy: camera=(), microphone=(), geolocation=()` header
- Static files and root path skip API key authentication
- Version bumped to 0.2.0

**Tests:**
- 131 unit tests (25 new tests for all new features)
- Tests for security headers, feedback store, chunks endpoint, stats endpoint, audit CSV export

### v0.1.0

- Initial release
- Core architecture: ingestion → processing → context assembly → reasoning
- GitHub ingestion (PRs, commits) with auto-pagination and retry
- Slack thread ingestion
- Semantic chunking by content type
- Temporal staleness tagging
- Entity linking (cross-reference resolution)
- Query classification (why/how/who/incident/general)
- Token-budget-aware context assembly
- Claude LLM integration with model routing and streaming
- API key authentication middleware
- Per-IP rate limiting
- Request logging with correlation IDs
- Permission-based content filtering
- Audit logging
- GitHub webhook receiver with signature verification
- Slack signature verification with replay protection
- Web UI with Ask, Ingest, Audit, and Status views
- 106 unit tests
