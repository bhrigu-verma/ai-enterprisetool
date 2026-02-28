"""Tests for settings validation."""

from __future__ import annotations

import os

import pytest

from src.config.settings import Settings, reset_settings


class TestSettingsValidation:
    def test_defaults_are_valid(self):
        s = Settings()
        assert s.max_context_tokens > 0
        assert s.staleness_threshold_days >= 0

    def test_negative_max_context_tokens_rejected(self):
        with pytest.raises(ValueError):
            Settings(max_context_tokens=-1)

    def test_negative_staleness_days_rejected(self):
        with pytest.raises(ValueError):
            Settings(staleness_threshold_days=-1)

    def test_zero_rate_limit_rejected(self):
        with pytest.raises(ValueError):
            Settings(rate_limit_per_minute=0)

    def test_api_keys_parsed_as_list(self):
        os.environ["AET_API_KEYS"] = '["key1", "key2"]'
        reset_settings()
        try:
            s = Settings()
            assert s.api_keys == ["key1", "key2"]
        finally:
            os.environ.pop("AET_API_KEYS", None)
            reset_settings()
