# US Stock Auto-Trading Engine

## Project Overview
Automated US stock trading system using Korea Investment & Securities (KIS) Open API.
Architecture inherited from ~/coin project (crypto trading bot).

## Tech Stack
- Backend: Python 3.12+, FastAPI, SQLAlchemy 2.0 (asyncpg), PostgreSQL, Redis
- Frontend: React 18, TypeScript, Vite, TailwindCSS
- Strategy config: config/strategies.yaml (YAML-based parameter management)
- Testing: pytest + pytest-asyncio + pytest-cov

## Core Rules

### Code
- All code must have unit tests (no untested code commits)
- Async functions use async/await pattern (asyncpg, aiohttp)
- External API calls must have error handling + retry logic
- Type hints required (mypy strict compatible)
- Pydantic models for data validation
- Never hardcode strategy parameters in code — use config/strategies.yaml

### Strategy Rules
- New strategies must pass backtest before activation (CAGR>12%, Sharpe>1.0, MDD<25%)
- Inherit BaseStrategy, implement analyze() -> Signal
- Strategy weights defined per market state in profiles section of strategies.yaml
- Start new strategies at weight 0.05, increase gradually after paper validation

### Testing Requirements
- Unit tests: pytest + pytest-asyncio, coverage target 90%+
- Scenario tests: tests/scenarios/ (core trading flows)
- Backtest: required before any strategy goes live
- DB tests: aiosqlite in-memory (test isolation)
- External APIs: always mock (KIS, yfinance, Claude)

### Commits & PRs
- Conventional Commits: feat/fix/refactor/test/docs/config/ci
- PR requires all tests passing before merge
- Strategy change PRs must include backtest results

### Directory Layout
- backend/exchange/: Exchange adapters (KIS REST, KIS WebSocket, Paper)
- backend/strategies/: Trading strategies (1 file per strategy)
- backend/engine/: Trading engine (order, position, risk management)
- backend/scanner/: Stock scanning (3-Layer pipeline: Indicator -> yfinance -> AI)
- backend/data/: Data services (market data, indicators, external data)
- backend/agents/: AI agents (market analysis, risk, trade review)
- backend/api/: REST + WebSocket endpoints
- backend/backtest/: Backtesting engine
- config/: Strategy & ETF YAML config files
- docs/: Architecture, API reference, guides

### Key Architecture Decisions
- KIS API rate limit: 20 req/sec (real), 5 req/sec (paper) — use RateLimiter
- KIS WebSocket: max 41 subscriptions per session — priority-based rotation
- US stock real-time data via KIS is delayed (~15min) — supplement with yfinance
- 3-Layer screening: IndicatorScreener (tech only) -> FundamentalEnricher (yfinance) -> AI (Claude)
- Dual engine: US Stock Engine (individual stocks) + ETF Engine (leveraged/inverse)
- All strategy params in config/strategies.yaml with runtime hot-reload
- 13 strategies total: 10 original + 3 ported from coin project (cis_momentum, larry_williams, bnf_deviation)
- Coin strategy adaptations: 4h crypto → 1D stocks, thresholds adjusted (e.g. BNF deviation -10%→-5%)
- Port separation: us-stock 8001/3001, coin 8000/3000
- Shared infra: PostgreSQL (coin's container, separate DB), Redis db 1 (coin uses db 0)
- Notification: adapter pattern (Discord/Telegram/Slack)

### Reference
- ~/coin: Crypto trading bot (architecture reference)
- SYSTEM_DESIGN.md: Full system design document
- config/strategies.yaml: Strategy parameters and weights
