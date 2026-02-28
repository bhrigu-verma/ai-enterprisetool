"""Security utilities — permission filtering, audit logging, and webhook verification.

Enterprise requirements addressed:
- Permission filtering inherits from source access controls
- Audit logging is append-only with timestamps for compliance
- Webhook verification uses constant-time comparison to prevent timing attacks
- Slack signatures include timestamp validation to prevent replay attacks
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone

from src.models.schemas import AuditEntry, Chunk

logger = logging.getLogger(__name__)

# Maximum age (seconds) for a Slack request signature to be considered valid
_SLACK_SIGNATURE_MAX_AGE = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Permission filter
# ---------------------------------------------------------------------------

class PermissionFilter:
    """Filters retrieved chunks based on the requesting user's access rights.

    *user_permissions* is a set of permission strings (e.g. repo names,
    channel IDs) that the user is allowed to access.

    Rules:
    - If ``user_permissions`` is empty, no filtering is applied (all allowed).
    - Chunks with *no* permission constraints are always accessible.
    - Chunks with permissions require at least one matching entry.
    """

    def filter(self, chunks: list[Chunk], user_permissions: set[str]) -> list[Chunk]:
        """Return only chunks the user is authorized to see."""
        if not user_permissions:
            return chunks  # no restrictions configured
        result: list[Chunk] = []
        for chunk in chunks:
            required = set(chunk.metadata.permissions)
            if not required or required & user_permissions:
                result.append(chunk)
        return result


# ---------------------------------------------------------------------------
# Audit logger
# ---------------------------------------------------------------------------

class AuditLogger:
    """Append-only audit log for every query and retrieval event.

    The in-memory store is suitable for development.  In production,
    entries are persisted to PostgreSQL via the ``AuditRow`` model.
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def log(
        self,
        *,
        user_id: str,
        query: str,
        response_summary: str = "",
        chunks_retrieved: list[str] | None = None,
    ) -> AuditEntry:
        if not user_id:
            raise ValueError("user_id is required for audit logging")
        entry = AuditEntry(
            user_id=user_id,
            query=query,
            response_summary=response_summary,
            chunks_retrieved=chunks_retrieved or [],
            timestamp=datetime.now(timezone.utc),
        )
        self._entries.append(entry)
        logger.info(
            "AUDIT | user=%s query=%r chunks=%d",
            user_id,
            query[:100],
            len(entry.chunks_retrieved),
        )
        return entry

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def clear(self) -> None:
        """Clear entries (for testing only)."""
        self._entries.clear()


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------

def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify a GitHub webhook ``X-Hub-Signature-256`` header.

    Uses constant-time comparison to prevent timing attacks.
    """
    if not signature or not secret:
        return False
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def verify_slack_signature(
    payload: bytes, timestamp: str, signature: str, secret: str
) -> bool:
    """Verify a Slack request signature with replay protection.

    Rejects requests older than ``_SLACK_SIGNATURE_MAX_AGE`` seconds to
    prevent replay attacks.
    """
    if not signature or not secret or not timestamp:
        return False

    # Replay protection: reject old requests
    try:
        request_time = int(timestamp)
    except (ValueError, TypeError):
        return False

    if abs(time.time() - request_time) > _SLACK_SIGNATURE_MAX_AGE:
        logger.warning("Slack signature rejected: timestamp too old (%s)", timestamp)
        return False

    base = f"v0:{timestamp}:{payload.decode()}"
    expected = hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"v0={expected}", signature)
