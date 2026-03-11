"""Tests for news sentiment API."""

from api.news import update_sentiment_cache, _last_summary, _last_signals


import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from api.news import router, update_sentiment_cache
import api.news as news_module


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def reset_cache():
    news_module._last_summary = None
    news_module._last_signals = []
    news_module._last_updated = None
    yield
    news_module._last_summary = None
    news_module._last_signals = []
    news_module._last_updated = None


@pytest.mark.asyncio
async def test_sentiment_empty(app, reset_cache):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/news/sentiment")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["market_sentiment"] == 0.0
    assert data["summary"]["analyzed_count"] == 0
    assert data["signals"] == []
    assert data["updated_at"] is None


@pytest.mark.asyncio
async def test_sentiment_with_data(app, reset_cache):
    update_sentiment_cache(
        summary_dict={
            "symbol_sentiments": {"AAPL": 0.5, "TSLA": -0.3},
            "sector_sentiments": {"Technology": 0.4},
            "market_sentiment": 0.2,
            "actionable_count": 1,
            "analyzed_count": 10,
        },
        signals=[{
            "symbol": "AAPL",
            "sentiment": 0.5,
            "impact": "HIGH",
            "category": "earnings",
            "sector_impact": ["Technology"],
            "key_event": "Strong earnings beat",
            "trading_signal": "BULLISH",
            "time_sensitivity": "IMMEDIATE",
            "is_actionable": True,
        }],
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/news/sentiment")
    data = resp.json()
    assert data["summary"]["market_sentiment"] == 0.2
    assert data["summary"]["symbol_sentiments"]["AAPL"] == 0.5
    assert len(data["signals"]) == 1
    assert data["signals"][0]["symbol"] == "AAPL"
    assert data["updated_at"] is not None


def test_update_sentiment_cache(reset_cache):
    update_sentiment_cache(
        {"market_sentiment": 0.1, "analyzed_count": 5},
        [{"symbol": "GOOG", "sentiment": 0.3}],
    )
    assert news_module._last_summary["market_sentiment"] == 0.1
    assert len(news_module._last_signals) == 1
    assert news_module._last_updated is not None
