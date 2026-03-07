"""Tests for AI Market Analyst Agent."""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from agents.market_analyst import MarketAnalystAgent, AIRecommendation, SYSTEM_PROMPT


class TestMarketAnalyst:
    async def test_no_api_key_returns_default(self):
        agent = MarketAnalystAgent(api_key="")
        result = await agent.analyze(
            symbol="AAPL", indicator_score=75,
            fundamental_data={}, market_context={},
        )
        assert result.symbol == "AAPL"
        assert result.recommendation == "HOLD"

    async def test_parse_valid_json(self):
        agent = MarketAnalystAgent(api_key="test")
        raw = json.dumps({
            "symbol": "AAPL",
            "recommendation": "BUY",
            "conviction": "HIGH",
            "score": 85,
            "entry_timing": "NOW",
            "target_price": 200.0,
            "stop_loss_price": 155.0,
            "position_size": "FULL",
            "time_horizon": "MEDIUM",
            "key_reasons": ["Strong trend", "Good fundamentals"],
            "risks": ["Overbought RSI"],
            "summary": "AAPL looks strong.",
        })
        result = agent._parse_response("AAPL", raw)
        assert result.recommendation == "BUY"
        assert result.conviction == "HIGH"
        assert result.score == 85
        assert result.target_price == 200.0
        assert len(result.key_reasons) == 2

    async def test_parse_json_in_markdown(self):
        agent = MarketAnalystAgent(api_key="test")
        raw = '```json\n{"recommendation": "SELL", "conviction": "MEDIUM", "score": 30}\n```'
        result = agent._parse_response("AAPL", raw)
        assert result.recommendation == "SELL"
        assert result.score == 30

    async def test_parse_invalid_json(self):
        agent = MarketAnalystAgent(api_key="test")
        result = agent._parse_response("AAPL", "This is not JSON at all")
        assert result.symbol == "AAPL"
        assert result.recommendation == "HOLD"
        assert "This is not JSON" in result.summary

    async def test_build_prompt(self):
        agent = MarketAnalystAgent(api_key="test")
        prompt = agent._build_prompt(
            symbol="AAPL",
            indicator_score=80,
            fundamental_data={"pe_ratio": 28},
            market_context={"market_state": "uptrend"},
            current_price=175.0,
        )
        assert "AAPL" in prompt
        assert "$175.00" in prompt
        assert "80/100" in prompt

    async def test_analyze_with_mock_api(self):
        import sys

        mock_anthropic = MagicMock()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "recommendation": "STRONG_BUY",
            "conviction": "HIGH",
            "score": 90,
            "entry_timing": "NOW",
            "target_price": 200.0,
            "stop_loss_price": 160.0,
            "position_size": "FULL",
            "time_horizon": "MEDIUM",
            "key_reasons": ["Bull trend"],
            "risks": ["Market risk"],
            "summary": "Buy now.",
        }))]
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_anthropic.AsyncAnthropic.return_value = mock_client

        # Inject mock into sys.modules so `import anthropic` finds it
        original = sys.modules.get("anthropic")
        sys.modules["anthropic"] = mock_anthropic
        try:
            agent = MarketAnalystAgent(api_key="sk-test-key")
            result = await agent.analyze(
                symbol="AAPL", indicator_score=80,
                fundamental_data={}, market_context={},
                current_price=175.0,
            )
            assert result.recommendation == "STRONG_BUY"
            assert result.score == 90
        finally:
            if original is not None:
                sys.modules["anthropic"] = original
            else:
                sys.modules.pop("anthropic", None)


class TestAIRecommendation:
    def test_defaults(self):
        r = AIRecommendation(symbol="TEST")
        assert r.recommendation == "HOLD"
        assert r.conviction == "LOW"
        assert r.score == 50
        assert r.position_size == "SKIP"


class TestSystemPrompt:
    def test_prompt_contains_key_sections(self):
        assert "Technical Analysis" in SYSTEM_PROMPT
        assert "Fundamental Analysis" in SYSTEM_PROMPT
        assert "Risk Assessment" in SYSTEM_PROMPT
        assert "JSON" in SYSTEM_PROMPT
