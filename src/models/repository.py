"""Thread-safe in-memory chunk repository.

Serves as the default storage backend for development and testing.
In production this is replaced by PostgreSQL + Qdrant, but the interface
is identical so callers don't change.
"""

from __future__ import annotations

import threading
from typing import Sequence

from src.models.schemas import Chunk, SourceType


class ChunkRepository:
    """Thread-safe, in-memory chunk store with filtering capabilities."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chunks: dict[str, Chunk] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(self, chunk: Chunk) -> None:
        """Insert or update a single chunk (idempotent on ``chunk.id``)."""
        with self._lock:
            self._chunks[chunk.id] = chunk

    def add_many(self, chunks: Sequence[Chunk]) -> int:
        """Insert multiple chunks.  Returns the number actually stored."""
        with self._lock:
            for c in chunks:
                self._chunks[c.id] = c
        return len(chunks)

    def remove(self, chunk_id: str) -> bool:
        """Remove a chunk by ID.  Returns True if it existed."""
        with self._lock:
            return self._chunks.pop(chunk_id, None) is not None

    def clear(self) -> None:
        """Remove all chunks."""
        with self._lock:
            self._chunks.clear()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, chunk_id: str) -> Chunk | None:
        with self._lock:
            return self._chunks.get(chunk_id)

    def list_all(self) -> list[Chunk]:
        """Return a snapshot of all chunks (safe copy)."""
        with self._lock:
            return list(self._chunks.values())

    def filter_by_source_type(self, source_type: SourceType) -> list[Chunk]:
        with self._lock:
            return [c for c in self._chunks.values() if c.metadata.source_type == source_type]

    def filter_by_repo(self, repo: str) -> list[Chunk]:
        with self._lock:
            return [c for c in self._chunks.values() if c.metadata.repo == repo]

    def filter_by_permissions(self, user_permissions: set[str]) -> list[Chunk]:
        """Return only chunks the user is authorised to see.

        - Chunks with *no* permission constraints are accessible to everyone.
        - Chunks with permissions require at least one matching entry.
        """
        with self._lock:
            results: list[Chunk] = []
            for c in self._chunks.values():
                required = set(c.metadata.permissions)
                if not required or required & user_permissions:
                    results.append(c)
            return results

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._chunks)
