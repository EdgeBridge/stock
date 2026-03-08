"""AI Market Analyst Agent.

Layer 3 of the screening pipeline: LLM-based comprehensive analysis.
Combines indicator scores, fundamental data, and market context
to produce actionable trade recommendations.

Supports persistent memory: saves key insights after each analysis
and injects relevant past context into future prompts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.agent_context import AgentContextService
    from services.llm import LLMClient

logger = logging.getLogger(__name__)

AGENT_TYPE = "market_analyst"

SYSTEM_PROMPT = """You are a professional US stock market analyst AI assistant.
You analyze stocks using a combination of technical indicators, fundamental data,
and market context to provide actionable trading recommendations.

Your analysis framework:
1. **Technical Analysis**: EMA alignment, ADX trend strength, RSI momentum,
   MACD histogram, Bollinger Bands, support/resistance levels
2. **Fundamental Analysis**: Revenue growth, profit margins, PE ratio, PEG,
   free cash flow, debt levels
3. **Consensus**: Analyst ratings, price targets, recent upgrades/downgrades
4. **Smart Money**: Institutional ownership, insider activity, short interest
5. **Risk Assessment**: Volatility (ATR/BB width), drawdown risk, correlation
6. **Timing**: Entry timing relative to support/resistance, volume confirmation

Output your analysis as JSON with this exact structure:
{
  "symbol": "AAPL",
  "recommendation": "BUY" | "HOLD" | "SELL" | "STRONG_BUY" | "STRONG_SELL",
  "conviction": "HIGH" | "MEDIUM" | "LOW",
  "score": 0-100,
  "entry_timing": "NOW" | "WAIT_PULLBACK" | "WAIT_BREAKOUT" | "NOT_NOW",
  "target_price": 0.0,
  "stop_loss_price": 0.0,
  "position_size": "FULL" | "HALF" | "QUARTER" | "SKIP",
  "time_horizon": "SHORT" | "MEDIUM" | "LONG",
  "key_reasons": ["reason1", "reason2", "reason3"],
  "risks": ["risk1", "risk2"],
  "summary": "One paragraph summary"
}"""


@dataclass
class AIRecommendation:
    symbol: str
    recommendation: str = "HOLD"
    conviction: str = "LOW"
    score: int = 50
    entry_timing: str = "NOT_NOW"
    target_price: float = 0.0
    stop_loss_price: float = 0.0
    position_size: str = "SKIP"
    time_horizon: str = "MEDIUM"
    key_reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    summary: str = ""


class MarketAnalystAgent:
    """AI agent for comprehensive stock analysis using LLMClient."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        context_service: AgentContextService | None = None,
    ):
        self._llm_client = llm_client
        self._ctx = context_service

    async def analyze(
        self,
        symbol: str,
        indicator_score: float,
        fundamental_data: dict,
        market_context: dict,
        current_price: float = 0.0,
    ) -> AIRecommendation:
        """Analyze a stock using LLM.

        Args:
            symbol: Stock ticker
            indicator_score: Layer 1 technical score (0-100)
            fundamental_data: Layer 2 enrichment data
            market_context: Current market state, sector performance, etc.
            current_price: Current stock price
        """
        if not self._llm_client:
            logger.warning("No LLM client configured, returning default recommendation")
            return AIRecommendation(symbol=symbol)

        # Build context from past memories
        memory_context = ""
        if self._ctx:
            try:
                sector = fundamental_data.get("sector", "")
                memory_context = await self._ctx.build_context(
                    AGENT_TYPE, symbol=symbol, sector=sector, max_tokens=1500,
                )
            except Exception as e:
                logger.debug("Failed to load agent context: %s", e)

        user_prompt = self._build_prompt(
            symbol, indicator_score, fundamental_data,
            market_context, current_price, memory_context,
        )

        try:
            response = await self._llm_client.generate(
                messages=[{"role": "user", "content": user_prompt}],
                system=SYSTEM_PROMPT,
                max_tokens=1024,
            )
            result = self._parse_response(symbol, response.text or "")

            # Save insight to memory (fire-and-forget)
            if self._ctx and result.summary:
                await self._save_insight(symbol, result)

            return result

        except Exception as e:
            logger.error("AI analysis failed for %s: %s", symbol, e)
            return AIRecommendation(symbol=symbol)

    async def _save_insight(self, symbol: str, result: AIRecommendation) -> None:
        """Extract and save key insight from analysis result."""
        try:
            # Importance based on conviction + non-HOLD recommendation
            importance = 5
            if result.conviction == "HIGH":
                importance = 8
            elif result.conviction == "MEDIUM":
                importance = 6
            if result.recommendation in ("STRONG_BUY", "STRONG_SELL"):
                importance = min(10, importance + 2)

            insight = (
                f"{result.recommendation}(score={result.score}, "
                f"conviction={result.conviction}): {result.summary[:200]}"
            )
            await self._ctx.save(
                AGENT_TYPE, "symbol", symbol, insight, importance=importance,
            )
        except Exception as e:
            logger.debug("Failed to save agent insight: %s", e)

    def _build_prompt(
        self,
        symbol: str,
        indicator_score: float,
        fundamental_data: dict,
        market_context: dict,
        current_price: float,
        memory_context: str = "",
    ) -> str:
        parts = [
            f"Analyze {symbol} (current price: ${current_price:.2f})",
            f"\n## Technical Indicator Score: {indicator_score:.0f}/100",
            f"\n## Fundamental Data:\n{json.dumps(fundamental_data, indent=2, default=str)}",
            f"\n## Market Context:\n{json.dumps(market_context, indent=2, default=str)}",
        ]

        if memory_context:
            parts.append(f"\n{memory_context}")

        parts.append("\nProvide your comprehensive analysis and recommendation as JSON.")
        return "\n".join(parts)

    def _parse_response(self, symbol: str, text: str) -> AIRecommendation:
        """Parse LLM's JSON response into AIRecommendation."""
        try:
            # Extract JSON from response (may be wrapped in markdown)
            json_str = text
            if "```json" in text:
                json_str = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                json_str = text.split("```")[1].split("```")[0]

            data = json.loads(json_str.strip())
            return AIRecommendation(
                symbol=symbol,
                recommendation=data.get("recommendation", "HOLD"),
                conviction=data.get("conviction", "LOW"),
                score=int(data.get("score") or 50),
                entry_timing=data.get("entry_timing", "NOT_NOW"),
                target_price=float(data.get("target_price") or 0),
                stop_loss_price=float(data.get("stop_loss_price") or 0),
                position_size=data.get("position_size", "SKIP"),
                time_horizon=data.get("time_horizon", "MEDIUM"),
                key_reasons=data.get("key_reasons") or [],
                risks=data.get("risks") or [],
                summary=data.get("summary", ""),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("Failed to parse AI response for %s: %s", symbol, e)
            return AIRecommendation(symbol=symbol, summary=text[:500])
