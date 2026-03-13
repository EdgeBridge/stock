"""Tests for LLM client: daily budget, fallback chain order, call counting."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.llm.client import LLMClient
from services.llm.providers import LLMResponse


@pytest.fixture
def llm_config():
    cfg = MagicMock()
    cfg.api_key = "test-key"
    cfg.model = "claude-haiku-4-5-20251001"
    cfg.fallback_model = "claude-sonnet-4-6"
    cfg.gemini_api_key = "gemini-key"
    cfg.gemini_fallback_model = "gemini-3-flash-preview"
    cfg.max_daily_calls = 10
    return cfg


@pytest.fixture
def mock_response():
    return LLMResponse(
        text="test response",
        model="claude-haiku-4-5-20251001",
    )


class TestDailyBudget:
    def test_budget_check_passes_when_under_limit(self, llm_config):
        with patch("services.llm.client.AnthropicProvider"), \
             patch("services.llm.client.GeminiProvider"):
            client = LLMClient(llm_config)
            assert client._check_budget() is True

    def test_budget_check_fails_when_at_limit(self, llm_config):
        with patch("services.llm.client.AnthropicProvider"), \
             patch("services.llm.client.GeminiProvider"):
            client = LLMClient(llm_config)
            client._daily_calls = 10
            import time
            client._daily_reset_date = time.strftime("%Y-%m-%d")
            assert client._check_budget() is False

    def test_budget_resets_on_new_day(self, llm_config):
        with patch("services.llm.client.AnthropicProvider"), \
             patch("services.llm.client.GeminiProvider"):
            client = LLMClient(llm_config)
            client._daily_calls = 10
            client._daily_reset_date = "2020-01-01"  # old date
            assert client._check_budget() is True
            assert client._daily_calls == 0

    def test_unlimited_when_max_is_zero(self, llm_config):
        llm_config.max_daily_calls = 0
        with patch("services.llm.client.AnthropicProvider"), \
             patch("services.llm.client.GeminiProvider"):
            client = LLMClient(llm_config)
            client._daily_calls = 999
            assert client._check_budget() is True

    def test_remaining_calls(self, llm_config):
        with patch("services.llm.client.AnthropicProvider"), \
             patch("services.llm.client.GeminiProvider"):
            client = LLMClient(llm_config)
            assert client.daily_calls_remaining == 10
            client._increment_calls()
            client._increment_calls()
            assert client.daily_calls_remaining == 8

    def test_remaining_unlimited(self, llm_config):
        llm_config.max_daily_calls = 0
        with patch("services.llm.client.AnthropicProvider"), \
             patch("services.llm.client.GeminiProvider"):
            client = LLMClient(llm_config)
            assert client.daily_calls_remaining == -1

    @pytest.mark.asyncio
    async def test_generate_rejected_when_budget_exhausted(self, llm_config):
        with patch("services.llm.client.AnthropicProvider"), \
             patch("services.llm.client.GeminiProvider"):
            client = LLMClient(llm_config)
            import time
            client._daily_calls = 10
            client._daily_reset_date = time.strftime("%Y-%m-%d")

            with pytest.raises(RuntimeError, match="budget exhausted"):
                await client.generate(
                    messages=[{"role": "user", "content": "test"}],
                )

    @pytest.mark.asyncio
    async def test_generate_increments_counter(self, llm_config, mock_response):
        with patch("services.llm.client.AnthropicProvider") as MockAnthropic, \
             patch("services.llm.client.GeminiProvider"):
            mock_provider = MockAnthropic.return_value
            mock_provider.create = AsyncMock(return_value=mock_response)

            client = LLMClient(llm_config)
            assert client._daily_calls == 0

            await client.generate(
                messages=[{"role": "user", "content": "test"}],
            )
            assert client._daily_calls == 1


class TestFallbackChain:
    def test_chain_order_is_haiku_gemini_sonnet(self, llm_config):
        """Gemini (free) should come before Sonnet (expensive)."""
        with patch("services.llm.client.AnthropicProvider") as MockA, \
             patch("services.llm.client.GeminiProvider") as MockG:
            client = LLMClient(llm_config)
            chain = client._build_fallback_chain()

            models = [model for model, _ in chain]
            assert models[0] == "claude-haiku-4-5-20251001"
            assert models[1] == "gemini-3-flash-preview"
            assert models[2] == "claude-sonnet-4-6"

    def test_model_override_skips_sonnet_fallback(self, llm_config):
        """When model_override is set, don't fall back to Sonnet."""
        with patch("services.llm.client.AnthropicProvider"), \
             patch("services.llm.client.GeminiProvider"):
            client = LLMClient(llm_config)
            chain = client._build_fallback_chain(model_override="gemini-3-flash-preview")

            models = [model for model, _ in chain]
            assert "gemini-3-flash-preview" in models
            assert "claude-sonnet-4-6" not in models

    def test_chain_without_gemini(self, llm_config):
        llm_config.gemini_api_key = ""
        llm_config.gemini_fallback_model = ""
        with patch("services.llm.client.AnthropicProvider"):
            client = LLMClient(llm_config)
            chain = client._build_fallback_chain()

            models = [model for model, _ in chain]
            assert len(models) == 2
            assert models[0] == "claude-haiku-4-5-20251001"
            assert models[1] == "claude-sonnet-4-6"
