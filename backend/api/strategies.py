"""Strategy API endpoints."""

from fastapi import APIRouter, Depends

from api.dependencies import get_registry
from strategies.registry import StrategyRegistry

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("/")
async def list_strategies(registry: StrategyRegistry = Depends(get_registry)):
    """List all strategies and their status."""
    strategies = registry.get_all()
    return [
        {
            "name": s.name,
            "display_name": s.display_name,
            "applicable_market_types": s.applicable_market_types,
            "timeframe": s.required_timeframe,
            "params": s.get_params(),
        }
        for s in strategies.values()
    ]


@router.get("/{name}/params")
async def get_strategy_params(
    name: str,
    registry: StrategyRegistry = Depends(get_registry),
):
    """Get parameters for a specific strategy."""
    strategy = registry.get(name)
    if not strategy:
        return {"error": f"Strategy '{name}' not found"}
    return {"name": name, "params": strategy.get_params()}


@router.post("/reload")
async def reload_config(registry: StrategyRegistry = Depends(get_registry)):
    """Hot-reload strategy configuration from YAML."""
    registry.reload_config()
    return {"status": "ok", "strategies": registry.get_names()}
