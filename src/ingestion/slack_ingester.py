"""Slack thread ingestion via the Slack Web API.

Production-grade features:
- Retry with exponential backoff on transient errors
- Input validation
- Proper error handling for Slack API error responses
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.config.resilience import retry_async
from src.models.schemas import SlackThread

logger = logging.getLogger(__name__)

_SLACK_API = "https://slack.com/api"
_DEFAULT_TIMEOUT = 30


class SlackIngester:
    """Fetches and normalises Slack threads from indexed channels."""

    def __init__(
        self,
        bot_token: str,
        indexed_channels: list[str] | None = None,
        *,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        if not bot_token:
            raise ValueError("Slack bot token is required")
        self._headers = {"Authorization": f"Bearer {bot_token}"}
        self._indexed_channels = indexed_channels or []
        self._timeout = timeout

    async def fetch_threads(
        self,
        channel_id: str,
        *,
        limit: int = 50,
        oldest: str | None = None,
    ) -> list[SlackThread]:
        """Return threads from a Slack channel as normalised *SlackThread* objects."""
        if not channel_id:
            raise ValueError("channel_id is required")

        messages = await self._list_messages(channel_id, limit=limit, oldest=oldest)
        threads: list[SlackThread] = []
        for msg in messages:
            thread_ts = msg.get("thread_ts") or msg.get("ts")
            if thread_ts is None:
                continue
            replies = await self._fetch_replies(channel_id, thread_ts)
            threads.append(
                SlackThread(
                    thread_id=f"{channel_id}:{thread_ts}",
                    channel=channel_id,
                    messages=[r.get("text", "") for r in replies if r.get("text")],
                    participants=list(
                        {r.get("user", "") for r in replies if r.get("user")}
                    ),
                    timestamp=_ts_to_datetime(thread_ts),
                )
            )

        logger.info("Fetched %d threads from channel %s", len(threads), channel_id)
        return threads

    # ------------------------------------------------------------------
    # Internal API calls
    # ------------------------------------------------------------------

    @retry_async(
        max_attempts=3,
        base_delay=1.0,
        retryable_exceptions=(httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException),
    )
    async def _list_messages(
        self, channel_id: str, *, limit: int = 50, oldest: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"channel": channel_id, "limit": min(limit, 200)}
        if oldest:
            params["oldest"] = oldest
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_SLACK_API}/conversations.history",
                headers=self._headers,
                params=params,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        if not data.get("ok"):
            error = data.get("error", "unknown")
            logger.warning("Slack API error: %s", error)
            raise RuntimeError(f"Slack API error: {error}")
        return data.get("messages", [])

    @retry_async(
        max_attempts=3,
        base_delay=1.0,
        retryable_exceptions=(httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException),
    )
    async def _fetch_replies(
        self, channel_id: str, thread_ts: str
    ) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_SLACK_API}/conversations.replies",
                headers=self._headers,
                params={"channel": channel_id, "ts": thread_ts, "limit": 200},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        if not data.get("ok"):
            return []
        return data.get("messages", [])


def _ts_to_datetime(ts: str) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (ValueError, TypeError):
        return None
