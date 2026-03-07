"""API dependency injection helpers."""

from fastapi import Request

from exchange.base import ExchangeAdapter
from data.market_data_service import MarketDataService
from data.indicator_service import IndicatorService
from data.external_data_service import ExternalDataService
from engine.risk_manager import RiskManager
from engine.order_manager import OrderManager
from strategies.registry import StrategyRegistry
from strategies.combiner import SignalCombiner
from services.rate_limiter import RateLimiter


def get_adapter(request: Request) -> ExchangeAdapter:
    return request.app.state.adapter


def get_market_data(request: Request) -> MarketDataService:
    return request.app.state.market_data


def get_registry(request: Request) -> StrategyRegistry:
    return request.app.state.registry


def get_order_manager(request: Request) -> OrderManager:
    return request.app.state.order_manager


def get_risk_manager(request: Request) -> RiskManager:
    return request.app.state.risk_manager
