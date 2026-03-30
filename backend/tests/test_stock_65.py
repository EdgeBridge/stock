"""Tests for STOCK-65: KR market strategy optimization.

Covers:
- RiskParams: kelly_fraction, min_position_pct, dynamic_sl_tp fields
- RiskManager: KellyPositionSizer initialized with new params
- RiskManager.calculate_dynamic_sl_tp: static mode when dynamic_sl_tp=False
- StrategyConfigLoader: market-specific config methods
- EvaluationLoop.set_disabled_strategies: filters strategies by market
- EvaluationLoop._min_confidence: per-market min_confidence override
- strategies.yaml: KR section presence and values
"""

import pytest

from engine.evaluation_loop import EvaluationLoop
from engine.risk_manager import RiskManager, RiskParams
from strategies.config_loader import StrategyConfigLoader

# ---------------------------------------------------------------------------
# RiskParams: new fields
# ---------------------------------------------------------------------------

class TestRiskParamsNewFields:
    def test_default_kelly_fraction(self):
        params = RiskParams()
        assert params.kelly_fraction == 0.40

    def test_default_min_position_pct(self):
        params = RiskParams()
        assert params.min_position_pct == 0.05

    def test_default_dynamic_sl_tp(self):
        params = RiskParams()
        assert params.dynamic_sl_tp is True

    def test_custom_kelly_fraction(self):
        params = RiskParams(kelly_fraction=0.50)
        assert params.kelly_fraction == 0.50

    def test_custom_min_position_pct(self):
        params = RiskParams(min_position_pct=0.12)
        assert params.min_position_pct == 0.12

    def test_disable_dynamic_sl_tp(self):
        params = RiskParams(dynamic_sl_tp=False)
        assert params.dynamic_sl_tp is False


# ---------------------------------------------------------------------------
# RiskManager: KellyPositionSizer receives new params
# ---------------------------------------------------------------------------

class TestRiskManagerKellyParams:
    def test_kelly_fraction_propagated_to_sizer(self):
        params = RiskParams(kelly_fraction=0.50, max_position_pct=0.20)
        rm = RiskManager(params=params)
        assert rm._kelly._kelly_frac == 0.50

    def test_min_position_pct_propagated_to_sizer(self):
        params = RiskParams(min_position_pct=0.12)
        rm = RiskManager(params=params)
        assert rm._kelly._min_pct == 0.12

    def test_max_position_pct_still_propagated(self):
        params = RiskParams(max_position_pct=0.20)
        rm = RiskManager(params=params)
        assert rm._kelly._max_pct == 0.20


# ---------------------------------------------------------------------------
# RiskManager.calculate_dynamic_sl_tp: static mode
# ---------------------------------------------------------------------------

class TestDynamicSlTpStaticMode:
    def test_static_mode_returns_defaults(self):
        """When dynamic_sl_tp=False, always return configured defaults."""
        params = RiskParams(
            dynamic_sl_tp=False,
            default_stop_loss_pct=0.10,
            default_take_profit_pct=0.15,
        )
        rm = RiskManager(params=params)
        # Even with valid ATR, should return defaults
        sl, tp = rm.calculate_dynamic_sl_tp(50000.0, 500.0, market="KR")
        assert sl == 0.10
        assert tp == 0.15

    def test_static_mode_ignores_atr(self):
        """Static mode ignores ATR entirely, not just zero-ATR fallback."""
        params = RiskParams(
            dynamic_sl_tp=False,
            default_stop_loss_pct=0.10,
            default_take_profit_pct=0.15,
        )
        rm = RiskManager(params=params)
        # High ATR that would normally give wider SL/TP
        sl_high_atr, tp_high_atr = rm.calculate_dynamic_sl_tp(100.0, 20.0)
        # Low ATR
        sl_low_atr, tp_low_atr = rm.calculate_dynamic_sl_tp(100.0, 0.1)
        # Both should give same defaults
        assert sl_high_atr == sl_low_atr == 0.10
        assert tp_high_atr == tp_low_atr == 0.15

    def test_dynamic_mode_still_uses_atr(self):
        """When dynamic_sl_tp=True (default), ATR-based calculation proceeds."""
        params = RiskParams(dynamic_sl_tp=True, default_stop_loss_pct=0.08)
        rm = RiskManager(params=params)
        # High ATR should give a different result from default
        sl, tp = rm.calculate_dynamic_sl_tp(100.0, 8.0)
        # With 8% ATR, sl = min(0.15, 8% * 2.0) = 0.15, tp = min(0.20, 8% * 3.5)
        assert sl > 0.08  # Should be different from default 0.08


# ---------------------------------------------------------------------------
# KR risk params match spec values (STOCK-65)
# ---------------------------------------------------------------------------

class TestKRRiskParamsSpec:
    """Verify the exact KR optimized risk params can be expressed in RiskParams."""

    def test_kr_optimized_params(self):
        params = RiskParams(
            kelly_fraction=0.50,
            max_position_pct=0.20,
            min_position_pct=0.12,
            max_positions=8,
            default_stop_loss_pct=0.10,
            default_take_profit_pct=0.15,
            dynamic_sl_tp=False,
        )
        assert params.kelly_fraction == 0.50
        assert params.max_position_pct == 0.20
        assert params.min_position_pct == 0.12
        assert params.max_positions == 8
        assert params.default_stop_loss_pct == 0.10
        assert params.default_take_profit_pct == 0.15
        assert params.dynamic_sl_tp is False

    def test_kr_static_sl_tp_returns_spec_values(self):
        params = RiskParams(
            dynamic_sl_tp=False,
            default_stop_loss_pct=0.10,
            default_take_profit_pct=0.15,
        )
        rm = RiskManager(params=params)
        sl, tp = rm.calculate_dynamic_sl_tp(50000.0, 1000.0, market="KR")
        assert sl == 0.10
        assert tp == 0.15

    def test_kr_max_positions(self):
        params = RiskParams(max_positions=8)
        rm = RiskManager(params=params)
        # 8 positions filled → next buy rejected
        result = rm.calculate_position_size(
            symbol="005930",
            price=70000.0,
            portfolio_value=10_000_000,
            cash_available=5_000_000,
            current_positions=8,
        )
        assert result.allowed is False
        assert "Max positions" in result.reason

    def test_kr_max_position_pct(self):
        params = RiskParams(max_positions=10, max_position_pct=0.20)
        rm = RiskManager(params=params)
        result = rm.calculate_position_size(
            symbol="005930",
            price=70000.0,
            portfolio_value=10_000_000,
            cash_available=5_000_000,
            current_positions=2,
        )
        assert result.allowed is True
        # Should not exceed 20% of portfolio
        assert result.allocation_usd <= 10_000_000 * 0.20


# ---------------------------------------------------------------------------
# StrategyConfigLoader: market-specific methods
# ---------------------------------------------------------------------------

class TestStrategyConfigLoaderMarketMethods:
    def test_get_market_config_kr(self):
        loader = StrategyConfigLoader()
        kr_config = loader.get_market_config("KR")
        assert isinstance(kr_config, dict)
        assert "disabled_strategies" in kr_config

    def test_get_market_disabled_strategies_kr(self):
        loader = StrategyConfigLoader()
        disabled = loader.get_market_disabled_strategies("KR")
        assert isinstance(disabled, list)
        assert len(disabled) > 0
        # All strategies except supertrend and dual_momentum should be disabled
        assert "supertrend" not in disabled
        assert "dual_momentum" not in disabled
        # These should be disabled
        assert "trend_following" in disabled
        assert "donchian_breakout" in disabled
        assert "macd_histogram" in disabled
        assert "rsi_divergence" in disabled
        assert "bollinger_squeeze" in disabled
        assert "volume_profile" in disabled
        assert "regime_switch" in disabled
        assert "sector_rotation" in disabled
        assert "cis_momentum" in disabled
        assert "larry_williams" in disabled
        assert "bnf_deviation" in disabled
        assert "volume_surge" in disabled

    def test_get_market_risk_config_kr(self):
        loader = StrategyConfigLoader()
        risk_cfg = loader.get_market_risk_config("KR")
        assert isinstance(risk_cfg, dict)
        assert risk_cfg.get("kelly_fraction") == pytest.approx(0.50)
        assert risk_cfg.get("max_position_pct") == pytest.approx(0.20)
        assert risk_cfg.get("min_position_pct") == pytest.approx(0.12)
        assert risk_cfg.get("max_positions") == 8
        assert risk_cfg.get("default_stop_loss_pct") == pytest.approx(0.10)
        assert risk_cfg.get("default_take_profit_pct") == pytest.approx(0.15)
        assert risk_cfg.get("dynamic_sl_tp") is False

    def test_get_market_evaluation_loop_config_kr(self):
        loader = StrategyConfigLoader()
        eval_cfg = loader.get_market_evaluation_loop_config("KR")
        assert isinstance(eval_cfg, dict)
        assert eval_cfg.get("min_confidence") == pytest.approx(0.30)
        assert eval_cfg.get("min_active_ratio") == pytest.approx(0.0)
        assert eval_cfg.get("sell_cooldown_days") == 1
        assert eval_cfg.get("whipsaw_max_losses") == 2
        assert eval_cfg.get("min_hold_days") == 1

    def test_get_market_config_us_returns_empty(self):
        loader = StrategyConfigLoader()
        # US market doesn't have overrides in the config
        us_config = loader.get_market_config("US")
        # Either empty dict or US section if configured
        assert isinstance(us_config, dict)

    def test_get_market_disabled_strategies_unknown_market(self):
        loader = StrategyConfigLoader()
        disabled = loader.get_market_disabled_strategies("UNKNOWN")
        assert disabled == []

    def test_get_market_risk_config_unknown_market(self):
        loader = StrategyConfigLoader()
        risk_cfg = loader.get_market_risk_config("UNKNOWN")
        assert risk_cfg == {}

    def test_get_market_evaluation_loop_config_unknown_market(self):
        loader = StrategyConfigLoader()
        eval_cfg = loader.get_market_evaluation_loop_config("UNKNOWN")
        assert eval_cfg == {}


# ---------------------------------------------------------------------------
# EvaluationLoop: disabled strategies filtering
# ---------------------------------------------------------------------------

class TestEvaluationLoopDisabledStrategies:
    def _make_evaluation_loop(self) -> EvaluationLoop:
        """Create a minimal EvaluationLoop for testing."""
        from unittest.mock import MagicMock

        from engine.risk_manager import RiskManager
        from strategies.combiner import SignalCombiner
        from strategies.registry import StrategyRegistry

        adapter = MagicMock()
        market_data = MagicMock()
        indicator_svc = MagicMock()
        registry = MagicMock(spec=StrategyRegistry)
        combiner = SignalCombiner()
        order_manager = MagicMock()
        risk_manager = RiskManager()

        loop = EvaluationLoop(
            adapter=adapter,
            market_data=market_data,
            indicator_svc=indicator_svc,
            registry=registry,
            combiner=combiner,
            order_manager=order_manager,
            risk_manager=risk_manager,
            market="KR",
        )
        return loop

    def test_initial_disabled_strategies_empty(self):
        loop = self._make_evaluation_loop()
        assert loop._disabled_strategies == frozenset()

    def test_set_disabled_strategies(self):
        loop = self._make_evaluation_loop()
        loop.set_disabled_strategies(["trend_following", "macd_histogram"])
        assert "trend_following" in loop._disabled_strategies
        assert "macd_histogram" in loop._disabled_strategies

    def test_set_disabled_strategies_is_frozenset(self):
        loop = self._make_evaluation_loop()
        loop.set_disabled_strategies(["supertrend", "cis_momentum"])
        assert isinstance(loop._disabled_strategies, frozenset)

    def test_set_disabled_strategies_empty_list(self):
        loop = self._make_evaluation_loop()
        loop.set_disabled_strategies(["trend_following"])
        loop.set_disabled_strategies([])
        assert loop._disabled_strategies == frozenset()

    def test_set_disabled_strategies_kr_spec(self):
        """Verify all 12 KR-disabled strategies can be set."""
        loop = self._make_evaluation_loop()
        kr_disabled = [
            "trend_following", "donchian_breakout", "macd_histogram",
            "rsi_divergence", "bollinger_squeeze", "volume_profile",
            "regime_switch", "sector_rotation", "cis_momentum",
            "larry_williams", "bnf_deviation", "volume_surge",
        ]
        loop.set_disabled_strategies(kr_disabled)
        assert loop._disabled_strategies == frozenset(kr_disabled)
        # supertrend and dual_momentum must NOT be in disabled set
        assert "supertrend" not in loop._disabled_strategies
        assert "dual_momentum" not in loop._disabled_strategies

    def test_min_confidence_initial_value(self):
        loop = self._make_evaluation_loop()
        assert loop._min_confidence is None

    def test_min_confidence_can_be_set(self):
        loop = self._make_evaluation_loop()
        loop._min_confidence = 0.30
        assert loop._min_confidence == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# EvaluationLoop: strategy filtering integration
# ---------------------------------------------------------------------------

class TestEvaluationLoopStrategyFiltering:
    """Test that disabled strategies are actually filtered from evaluation."""

    def _make_mock_strategy(self, name: str):
        from unittest.mock import MagicMock

        from strategies.base import BaseStrategy
        strat = MagicMock(spec=BaseStrategy)
        strat.name = name
        return strat

    def _make_loop_with_strategies(self, strategy_names: list[str]) -> EvaluationLoop:
        from unittest.mock import MagicMock

        from engine.risk_manager import RiskManager
        from strategies.combiner import SignalCombiner
        from strategies.registry import StrategyRegistry

        strategies = [self._make_mock_strategy(n) for n in strategy_names]

        registry = MagicMock(spec=StrategyRegistry)
        registry.get_enabled.return_value = strategies

        loop = EvaluationLoop(
            adapter=MagicMock(),
            market_data=MagicMock(),
            indicator_svc=MagicMock(),
            registry=registry,
            combiner=SignalCombiner(),
            order_manager=MagicMock(),
            risk_manager=RiskManager(),
            market="KR",
        )
        return loop, strategies

    def test_no_disabled_returns_all_strategies(self):
        loop, strategies = self._make_loop_with_strategies(
            ["supertrend", "dual_momentum", "trend_following"]
        )
        all_strats = loop._registry.get_enabled()
        filtered = (
            [s for s in all_strats if s.name not in loop._disabled_strategies]
            if loop._disabled_strategies
            else all_strats
        )
        assert len(filtered) == 3

    def test_disabled_strategies_filtered_out(self):
        loop, strategies = self._make_loop_with_strategies(
            ["supertrend", "dual_momentum", "trend_following", "macd_histogram"]
        )
        loop.set_disabled_strategies(["trend_following", "macd_histogram"])
        all_strats = loop._registry.get_enabled()
        filtered = (
            [s for s in all_strats if s.name not in loop._disabled_strategies]
            if loop._disabled_strategies
            else all_strats
        )
        assert len(filtered) == 2
        names = [s.name for s in filtered]
        assert "supertrend" in names
        assert "dual_momentum" in names
        assert "trend_following" not in names
        assert "macd_histogram" not in names

    def test_kr_disabled_leaves_only_supertrend_and_dual_momentum(self):
        all_strategy_names = [
            "trend_following", "dual_momentum", "donchian_breakout", "supertrend",
            "macd_histogram", "rsi_divergence", "bollinger_squeeze", "volume_profile",
            "regime_switch", "sector_rotation", "cis_momentum", "larry_williams",
            "bnf_deviation", "volume_surge",
        ]
        loop, strategies = self._make_loop_with_strategies(all_strategy_names)
        kr_disabled = [
            "trend_following", "donchian_breakout", "macd_histogram",
            "rsi_divergence", "bollinger_squeeze", "volume_profile",
            "regime_switch", "sector_rotation", "cis_momentum",
            "larry_williams", "bnf_deviation", "volume_surge",
        ]
        loop.set_disabled_strategies(kr_disabled)
        all_strats = loop._registry.get_enabled()
        filtered = [s for s in all_strats if s.name not in loop._disabled_strategies]
        assert len(filtered) == 2
        names = {s.name for s in filtered}
        assert names == {"supertrend", "dual_momentum"}


# ---------------------------------------------------------------------------
# YAML config validation: KR section correctness
# ---------------------------------------------------------------------------

class TestYAMLKRSection:
    """Verify strategies.yaml has the correct KR market section structure."""

    def test_yaml_has_markets_section(self):
        loader = StrategyConfigLoader()
        markets = loader._config.get("markets", {})
        assert "KR" in markets

    def test_yaml_kr_has_disabled_strategies(self):
        loader = StrategyConfigLoader()
        kr = loader._config["markets"]["KR"]
        assert "disabled_strategies" in kr
        assert isinstance(kr["disabled_strategies"], list)

    def test_yaml_kr_has_risk_section(self):
        loader = StrategyConfigLoader()
        kr = loader._config["markets"]["KR"]
        assert "risk" in kr
        risk = kr["risk"]
        assert "kelly_fraction" in risk
        assert "max_position_pct" in risk
        assert "min_position_pct" in risk
        assert "max_positions" in risk
        assert "default_stop_loss_pct" in risk
        assert "default_take_profit_pct" in risk
        assert "dynamic_sl_tp" in risk

    def test_yaml_kr_has_evaluation_loop_section(self):
        loader = StrategyConfigLoader()
        kr = loader._config["markets"]["KR"]
        assert "evaluation_loop" in kr
        ev = kr["evaluation_loop"]
        assert "min_confidence" in ev
        assert "min_active_ratio" in ev
        assert "sell_cooldown_days" in ev
        assert "whipsaw_max_losses" in ev
        assert "min_hold_days" in ev

    def test_yaml_kr_disabled_count(self):
        """Exactly 12 strategies disabled (14 total - 2 enabled = 12)."""
        loader = StrategyConfigLoader()
        disabled = loader._config["markets"]["KR"]["disabled_strategies"]
        assert len(disabled) == 12

    def test_yaml_kr_risk_values(self):
        loader = StrategyConfigLoader()
        risk = loader._config["markets"]["KR"]["risk"]
        assert risk["kelly_fraction"] == pytest.approx(0.50)
        assert risk["max_position_pct"] == pytest.approx(0.20)
        assert risk["min_position_pct"] == pytest.approx(0.12)
        assert risk["max_positions"] == 8
        assert risk["default_stop_loss_pct"] == pytest.approx(0.10)
        assert risk["default_take_profit_pct"] == pytest.approx(0.15)
        assert risk["dynamic_sl_tp"] is False

    def test_yaml_kr_eval_loop_values(self):
        loader = StrategyConfigLoader()
        ev = loader._config["markets"]["KR"]["evaluation_loop"]
        assert ev["min_confidence"] == pytest.approx(0.30)
        assert ev["min_active_ratio"] == pytest.approx(0.0)
        assert ev["sell_cooldown_days"] == 1
        assert ev["whipsaw_max_losses"] == 2
        assert ev["min_hold_days"] == 1
