"""Tests for hard_sl_pct config loading (STOCK-61)."""

from pathlib import Path

import yaml

from strategies.config_loader import StrategyConfigLoader


class TestConfigLoaderHardSL:
    """Test hard_sl_pct loading from strategies.yaml config."""

    def test_get_hard_sl_pct_from_yaml(self, tmp_path: Path):
        """hard_sl_pct should be loaded from global config."""
        config = {
            "global": {
                "hard_sl_pct": -0.15,
            },
            "strategies": {},
        }
        config_file = tmp_path / "strategies.yaml"
        config_file.write_text(yaml.dump(config))

        loader = StrategyConfigLoader(config_file)
        result = loader.get_hard_sl_pct()

        assert result == -0.15

    def test_get_hard_sl_pct_default_when_missing(self, tmp_path: Path):
        """hard_sl_pct should default to -0.15 when missing from config."""
        config = {"global": {}, "strategies": {}}
        config_file = tmp_path / "strategies.yaml"
        config_file.write_text(yaml.dump(config))

        loader = StrategyConfigLoader(config_file)
        result = loader.get_hard_sl_pct()

        assert result == -0.15

    def test_get_hard_sl_pct_custom_value(self, tmp_path: Path):
        """hard_sl_pct should support custom values like -0.20."""
        config = {
            "global": {
                "hard_sl_pct": -0.20,
            },
            "strategies": {},
        }
        config_file = tmp_path / "strategies.yaml"
        config_file.write_text(yaml.dump(config))

        loader = StrategyConfigLoader(config_file)
        result = loader.get_hard_sl_pct()

        assert result == -0.20

    def test_get_hard_sl_pct_reload(self, tmp_path: Path):
        """hard_sl_pct should be reloaded on config reload."""
        config = {
            "global": {"hard_sl_pct": -0.15},
            "strategies": {},
        }
        config_file = tmp_path / "strategies.yaml"
        config_file.write_text(yaml.dump(config))

        loader = StrategyConfigLoader(config_file)
        assert loader.get_hard_sl_pct() == -0.15

        # Update config and reload
        config["global"]["hard_sl_pct"] = -0.20
        config_file.write_text(yaml.dump(config))
        loader.reload()

        assert loader.get_hard_sl_pct() == -0.20

    def test_get_hard_sl_pct_returns_float(self, tmp_path: Path):
        """hard_sl_pct should always return a float."""
        config = {
            "global": {"hard_sl_pct": -0.15},
            "strategies": {},
        }
        config_file = tmp_path / "strategies.yaml"
        config_file.write_text(yaml.dump(config))

        loader = StrategyConfigLoader(config_file)
        result = loader.get_hard_sl_pct()

        assert isinstance(result, float)
        assert result == -0.15
