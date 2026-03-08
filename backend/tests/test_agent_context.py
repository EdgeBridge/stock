"""Tests for AgentContextService — persistent memory for AI agents."""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.models import Base, AgentMemory
from services.agent_context import AgentContextService, CHARS_PER_TOKEN, MAX_ENTRIES_PER_AGENT


@pytest_asyncio.fixture
async def ctx_service():
    """AgentContextService with in-memory SQLite."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = AgentContextService(factory)
    yield service

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_factory():
    """Raw session factory for direct DB inspection."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


class TestSave:
    async def test_save_creates_entry(self, ctx_service):
        await ctx_service.save("market_analyst", "symbol", "AAPL", "Bearish divergence forming")

        context = await ctx_service.build_context("market_analyst", symbol="AAPL")
        assert "Bearish divergence" in context

    async def test_save_empty_content_ignored(self, ctx_service):
        await ctx_service.save("market_analyst", "symbol", "AAPL", "")
        await ctx_service.save("market_analyst", "symbol", "AAPL", "   ")

        context = await ctx_service.build_context("market_analyst", symbol="AAPL")
        assert context == ""

    async def test_save_calculates_token_count(self, db_factory):
        service = AgentContextService(db_factory)
        content = "A" * 100  # 100 chars = ~25 tokens
        await service.save("market_analyst", "symbol", "AAPL", content)

        async with db_factory() as session:
            from sqlalchemy import select
            result = await session.execute(select(AgentMemory))
            entry = result.scalars().first()
            assert entry.token_count == 100 // CHARS_PER_TOKEN

    async def test_save_clamps_importance(self, db_factory):
        service = AgentContextService(db_factory)
        await service.save("risk", "market", None, "test", importance=0)
        await service.save("risk", "market", None, "test2", importance=15)

        async with db_factory() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(AgentMemory).order_by(AgentMemory.id)
            )
            entries = list(result.scalars().all())
            assert entries[0].importance == 1   # clamped from 0
            assert entries[1].importance == 10  # clamped from 15


class TestBuildContext:
    async def test_empty_when_no_memories(self, ctx_service):
        context = await ctx_service.build_context("market_analyst", symbol="AAPL")
        assert context == ""

    async def test_symbol_memories_included(self, ctx_service):
        await ctx_service.save("market_analyst", "symbol", "AAPL", "Strong uptrend")
        await ctx_service.save("market_analyst", "symbol", "MSFT", "Consolidating")

        context = await ctx_service.build_context("market_analyst", symbol="AAPL")
        assert "Strong uptrend" in context
        assert "Consolidating" not in context  # different symbol

    async def test_market_memories_included(self, ctx_service):
        await ctx_service.save("market_analyst", "market", None, "VIX spike to 30")

        context = await ctx_service.build_context("market_analyst", symbol="AAPL")
        assert "VIX spike" in context

    async def test_lesson_memories_included(self, ctx_service):
        await ctx_service.save("trade_review", "lesson", "TSLA", "Avoid holding through earnings")

        context = await ctx_service.build_context("trade_review", symbol="NVDA")
        assert "Avoid holding" in context

    async def test_respects_token_budget(self, ctx_service):
        # Save many entries that exceed budget
        for i in range(20):
            await ctx_service.save(
                "market_analyst", "symbol", "AAPL",
                f"Insight {i}: " + "x" * 500,
                importance=5,
            )

        context = await ctx_service.build_context(
            "market_analyst", symbol="AAPL", max_tokens=200,
        )
        # Should not be empty but should be truncated
        assert context != ""
        # Total chars should be roughly within budget
        assert len(context) < 200 * CHARS_PER_TOKEN + 500  # some overhead for headers

    async def test_expired_memories_excluded(self, db_factory):
        service = AgentContextService(db_factory)

        # Insert an already-expired entry directly
        async with db_factory() as session:
            expired = AgentMemory(
                agent_type="market_analyst",
                category="symbol",
                symbol="AAPL",
                content="Old expired insight",
                token_count=10,
                importance=5,
                expires_at=datetime.utcnow() - timedelta(days=1),
            )
            session.add(expired)
            await session.commit()

        context = await service.build_context("market_analyst", symbol="AAPL")
        assert context == ""

    async def test_higher_importance_prioritized(self, ctx_service):
        await ctx_service.save("market_analyst", "symbol", "AAPL", "Low importance", importance=1)
        await ctx_service.save("market_analyst", "symbol", "AAPL", "High importance", importance=9)

        # With very small budget, only high importance should fit
        context = await ctx_service.build_context(
            "market_analyst", symbol="AAPL", max_tokens=30,
        )
        assert "High importance" in context

    async def test_agent_isolation(self, ctx_service):
        await ctx_service.save("market_analyst", "symbol", "AAPL", "Analyst insight")
        await ctx_service.save("risk", "market", None, "Risk insight")

        analyst_ctx = await ctx_service.build_context("market_analyst", symbol="AAPL")
        risk_ctx = await ctx_service.build_context("risk")

        assert "Analyst insight" in analyst_ctx
        assert "Risk insight" not in analyst_ctx
        assert "Risk insight" in risk_ctx
        assert "Analyst insight" not in risk_ctx

    async def test_context_has_age_labels(self, ctx_service):
        await ctx_service.save("market_analyst", "symbol", "AAPL", "Recent insight")

        context = await ctx_service.build_context("market_analyst", symbol="AAPL")
        assert "[today]" in context or "[0d ago]" in context


class TestCleanup:
    async def test_cleanup_expired(self, db_factory):
        service = AgentContextService(db_factory)

        # Insert one valid + one expired
        async with db_factory() as session:
            valid = AgentMemory(
                agent_type="risk", category="market", symbol=None,
                content="Valid", token_count=5, importance=5,
                expires_at=datetime.utcnow() + timedelta(days=7),
            )
            expired = AgentMemory(
                agent_type="risk", category="market", symbol=None,
                content="Expired", token_count=5, importance=5,
                expires_at=datetime.utcnow() - timedelta(days=1),
            )
            session.add_all([valid, expired])
            await session.commit()

        count = await service.cleanup_expired()
        assert count == 1

        # Only valid remains
        context = await service.build_context("risk")
        assert "Valid" in context
        assert "Expired" not in context

    async def test_enforce_limits(self, db_factory):
        service = AgentContextService(db_factory)

        # Insert MAX + 10 entries
        async with db_factory() as session:
            for i in range(MAX_ENTRIES_PER_AGENT + 10):
                entry = AgentMemory(
                    agent_type="market_analyst",
                    category="symbol",
                    symbol="TEST",
                    content=f"Entry {i}",
                    token_count=5,
                    importance=1 if i < 10 else 5,  # first 10 are low importance
                    expires_at=datetime.utcnow() + timedelta(days=7),
                )
                session.add(entry)
            await session.commit()

        trimmed = await service.enforce_limits("market_analyst")
        assert trimmed == 10  # removed the excess low-importance entries


class TestIntegrationWithAgent:
    """Verify agents work with and without context service."""

    async def test_market_analyst_without_context(self):
        """Agent works fine when context_service is None."""
        from agents.market_analyst import MarketAnalystAgent
        agent = MarketAnalystAgent(llm_client=None, context_service=None)
        result = await agent.analyze("AAPL", 75, {}, {})
        assert result.recommendation == "HOLD"

    async def test_market_analyst_with_context(self, ctx_service):
        """Agent loads context and includes it in prompt."""
        from unittest.mock import AsyncMock, MagicMock
        from services.llm.providers import LLMResponse
        from agents.market_analyst import MarketAnalystAgent

        # Pre-populate memory
        await ctx_service.save("market_analyst", "symbol", "AAPL", "Previous: bullish trend")

        client = MagicMock()
        client.generate = AsyncMock(return_value=LLMResponse(
            text='{"recommendation": "BUY", "conviction": "HIGH", "score": 85, '
                 '"summary": "Strong momentum continues"}',
            model="test",
        ))

        agent = MarketAnalystAgent(llm_client=client, context_service=ctx_service)
        result = await agent.analyze("AAPL", 80, {"sector": "Technology"}, {}, 175.0)

        assert result.recommendation == "BUY"

        # Verify context was included in the prompt
        call_kwargs = client.generate.call_args.kwargs
        messages = call_kwargs.get("messages") or client.generate.call_args[0][0]
        prompt = messages[0]["content"]
        assert "Previous: bullish trend" in prompt

    async def test_risk_agent_without_context(self):
        from agents.risk_assessment import RiskAssessmentAgent
        agent = RiskAssessmentAgent(llm_client=None, context_service=None)
        result = await agent.assess_portfolio([], {}, {})
        assert result.overall_risk_level == "MEDIUM"

    async def test_trade_review_without_context(self):
        from agents.trade_review import TradeReviewAgent
        agent = TradeReviewAgent(llm_client=None, context_service=None)
        result = await agent.review_trade(
            "AAPL", "buy", 150.0, 165.0, 10, "momentum", 150.0, 5, {}, {},
        )
        assert result.grade == "C"
