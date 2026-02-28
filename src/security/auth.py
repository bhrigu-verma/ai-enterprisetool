"""Security utilities — permission filtering, audit logging, and webhook verification."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone

from src.models.schemas import AuditEntry, Chunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Permission filter
# ---------------------------------------------------------------------------

class PermissionFilter:
    """Filters retrieved chunks based on the requesting user's access rights.

    *user_permissions* is a set of permission strings (e.g. repo names, channel IDs)
    that the user is allowed to access.
    """

    def filter(self, chunks: list[Chunk], user_permissions: set[str]) -> list[Chunk]:
        """Return only chunks the user is authorised to see."""
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
    """Append-only audit log for every query and retrieval event."""

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
        entry = AuditEntry(
            user_id=user_id,
            query=query,
            response_summary=response_summary,
            chunks_retrieved=chunks_retrieved or [],
            timestamp=datetime.now(timezone.utc),
        )
        self._entries.append(entry)
        logger.info("AUDIT | user=%s query=%r chunks=%d", user_id, query, len(entry.chunks_retrieved))
        return entry

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------

def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify a GitHub webhook ``X-Hub-Signature-256`` header."""
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def verify_slack_signature(
    payload: bytes, timestamp: str, signature: str, secret: str
) -> bool:
    """Verify a Slack request signature."""
    base = f"v0:{timestamp}:{payload.decode()}"
    expected = hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"v0={expected}", signature)
