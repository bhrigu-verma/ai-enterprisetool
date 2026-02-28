"""Tests for the resilience utilities (retry decorator)."""

from __future__ import annotations

import pytest

from src.config.resilience import RetryExhaustedError, is_retryable_http_status, retry_async


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_succeeds_without_retry(self):
        call_count = 0

        @retry_async(max_attempts=3, base_delay=0.01)
        async def _fn():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await _fn()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self):
        call_count = 0

        @retry_async(max_attempts=3, base_delay=0.01, retryable_exceptions=(ValueError,))
        async def _fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "ok"

        result = await _fn()
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_retry_exhausted_after_max_attempts(self):
        @retry_async(max_attempts=2, base_delay=0.01, retryable_exceptions=(ValueError,))
        async def _fn():
            raise ValueError("always fails")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await _fn()
        assert exc_info.value.attempts == 2
        assert isinstance(exc_info.value.last_exception, ValueError)

    @pytest.mark.asyncio
    async def test_non_retryable_exception_raises_immediately(self):
        call_count = 0

        @retry_async(max_attempts=3, base_delay=0.01, retryable_exceptions=(ValueError,))
        async def _fn():
            nonlocal call_count
            call_count += 1
            raise TypeError("not retryable")

        with pytest.raises(TypeError):
            await _fn()
        assert call_count == 1


class TestIsRetryableHttpStatus:
    def test_retryable_codes(self):
        for code in (429, 500, 502, 503, 504):
            assert is_retryable_http_status(code) is True

    def test_non_retryable_codes(self):
        for code in (200, 201, 400, 401, 403, 404):
            assert is_retryable_http_status(code) is False
