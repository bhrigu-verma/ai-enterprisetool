"""Slack thread ingestion via the Slack Web API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.models.schemas import SlackThread

logger = logging.getLogger(__name__)

_SLACK_API = "https://slack.com/api"


class SlackIngester:
    """Fetches and normalises Slack threads from indexed channels."""

    def __init__(self, bot_token: str, indexed_channels: list[str] | None = None) -> None:
        self._headers = {"Authorization": f"Bearer {bot_token}"}
        self._indexed_channels = indexed_channels or []

    async def fetch_threads(
        self,
        channel_id: str,
        *,
        limit: int = 50,
        oldest: str | None = None,
    ) -> list[SlackThread]:
        """Return threads from a Slack channel as normalised *SlackThread* objects."""
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
                    messages=[r.get("text", "") for r in replies],
                    participants=list({r.get("user", "") for r in replies if r.get("user")}),
                    timestamp=_ts_to_datetime(thread_ts),
                )
            )
        return threads

    # ------------------------------------------------------------------
    # Internal API calls
    # ------------------------------------------------------------------

    async def _list_messages(
        self, channel_id: str, *, limit: int = 50, oldest: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"channel": channel_id, "limit": limit}
        if oldest:
            params["oldest"] = oldest
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_SLACK_API}/conversations.history",
                headers=self._headers,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        if not data.get("ok"):
            logger.warning("Slack API error: %s", data.get("error"))
            return []
        return data.get("messages", [])

    async def _fetch_replies(
        self, channel_id: str, thread_ts: str
    ) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_SLACK_API}/conversations.replies",
                headers=self._headers,
                params={"channel": channel_id, "ts": thread_ts, "limit": 200},
                timeout=30,
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
