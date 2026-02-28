"""Tests for the thread-safe chunk repository."""

from __future__ import annotations

import threading

from src.models.repository import ChunkRepository
from src.models.schemas import Chunk, ChunkMetadata, SourceType


def _make_chunk(
    chunk_id: str = "c1", repo: str = "", permissions: list[str] | None = None,
) -> Chunk:
    return Chunk(
        id=chunk_id,
        content="test content",
        metadata=ChunkMetadata(
            source_type=SourceType.PR_DESCRIPTION,
            source_id="PR-1",
            repo=repo,
            permissions=permissions or [],
        ),
    )


class TestChunkRepository:
    def test_add_and_get(self):
        repo = ChunkRepository()
        chunk = _make_chunk("c1")
        repo.add(chunk)
        assert repo.get("c1") is not None
        assert repo.count == 1

    def test_add_is_idempotent(self):
        repo = ChunkRepository()
        repo.add(_make_chunk("c1"))
        repo.add(_make_chunk("c1"))
        assert repo.count == 1

    def test_add_many(self):
        repo = ChunkRepository()
        chunks = [_make_chunk(f"c{i}") for i in range(10)]
        added = repo.add_many(chunks)
        assert added == 10
        assert repo.count == 10

    def test_remove(self):
        repo = ChunkRepository()
        repo.add(_make_chunk("c1"))
        assert repo.remove("c1") is True
        assert repo.remove("c1") is False
        assert repo.count == 0

    def test_clear(self):
        repo = ChunkRepository()
        repo.add_many([_make_chunk(f"c{i}") for i in range(5)])
        repo.clear()
        assert repo.count == 0

    def test_list_all_returns_copy(self):
        repo = ChunkRepository()
        repo.add(_make_chunk("c1"))
        all_chunks = repo.list_all()
        assert len(all_chunks) == 1
        all_chunks.clear()  # mutating the returned list shouldn't affect the repo
        assert repo.count == 1

    def test_filter_by_source_type(self):
        repo = ChunkRepository()
        repo.add(_make_chunk("c1"))
        repo.add(Chunk(
            id="c2",
            content="code",
            metadata=ChunkMetadata(source_type=SourceType.CODE, source_id="file.py"),
        ))
        prs = repo.filter_by_source_type(SourceType.PR_DESCRIPTION)
        assert len(prs) == 1

    def test_filter_by_repo(self):
        repo = ChunkRepository()
        repo.add(_make_chunk("c1", repo="acme/backend"))
        repo.add(_make_chunk("c2", repo="acme/frontend"))
        assert len(repo.filter_by_repo("acme/backend")) == 1

    def test_filter_by_permissions(self):
        repo = ChunkRepository()
        repo.add(_make_chunk("c1", permissions=["repo:backend"]))
        repo.add(_make_chunk("c2", permissions=["repo:frontend"]))
        repo.add(_make_chunk("c3"))  # no permissions → always visible

        result = repo.filter_by_permissions({"repo:backend"})
        assert len(result) == 2  # c1 + c3

    def test_thread_safety(self):
        """Multiple threads writing simultaneously should not corrupt the repository."""
        repo = ChunkRepository()
        errors: list[Exception] = []

        def _writer(start: int):
            try:
                for i in range(100):
                    repo.add(_make_chunk(f"chunk-{start}-{i}"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_writer, args=(t * 100,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert repo.count == 500
