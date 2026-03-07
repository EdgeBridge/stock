"""Strategy configuration loader from YAML."""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "strategies.yaml"


class StrategyConfigLoader:
    """Load and provide strategy parameters from strategies.yaml."""

    def __init__(self, config_path: Path | str | None = None):
        self._path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._config: dict = {}
        self.reload()

    def reload(self) -> None:
        """Reload configuration from YAML file."""
        try:
            with open(self._path) as f:
                self._config = yaml.safe_load(f) or {}
            logger.info("Strategy config loaded from %s", self._path)
        except FileNotFoundError:
            logger.warning("Strategy config not found at %s, using defaults", self._path)
            self._config = {}

    @property
    def global_config(self) -> dict:
        return self._config.get("global", {})

    def get_strategy_config(self, strategy_name: str) -> dict:
        """Get full config block for a strategy."""
        return self._config.get("strategies", {}).get(strategy_name, {})

    def get_strategy_params(self, strategy_name: str) -> dict:
        """Get just the params section for a strategy."""
        return self.get_strategy_config(strategy_name).get("params", {})

    def is_enabled(self, strategy_name: str) -> bool:
        return self.get_strategy_config(strategy_name).get("enabled", False)

    def get_profile_weights(self, market_state: str) -> dict[str, float]:
        """Get strategy weights for a market state profile."""
        return self._config.get("profiles", {}).get(market_state, {})

    def get_stop_loss_config(self, strategy_name: str) -> dict:
        return self.get_strategy_config(strategy_name).get("stop_loss", {})

    def get_screening_config(self) -> dict:
        return self._config.get("screening", {})
