"""News sentiment API endpoints."""

import logging
from datetime import datetime

from fastapi import APIRouter

router = APIRouter(prefix="/news", tags=["news"])
logger = logging.getLogger(__name__)

# Cached sentiment state — updated by scheduler task
_last_summary: dict | None = None
_last_signals: list[dict] = []
_last_updated: str | None = None


def update_sentiment_cache(
    summary_dict: dict,
    signals: list[dict],
) -> None:
    """Called from scheduler task to cache latest sentiment results."""
    global _last_summary, _last_signals, _last_updated
    _last_summary = summary_dict
    _last_signals = signals
    _last_updated = datetime.utcnow().isoformat()


@router.get("/sentiment")
async def get_sentiment():
    """Get latest news sentiment analysis results."""
    return {
        "summary": _last_summary or {
            "symbol_sentiments": {},
            "sector_sentiments": {},
            "market_sentiment": 0.0,
            "actionable_count": 0,
            "analyzed_count": 0,
        },
        "signals": _last_signals,
        "updated_at": _last_updated,
    }
