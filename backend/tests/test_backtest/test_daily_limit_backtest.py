"""Tests for daily buy limit + confidence escalation in backtest engine."""

import pytest

from backtest.full_pipeline import PipelineConfig, FullPipelineBacktest


class TestPipelineConfigDailyLimit:
    """PipelineConfig daily limit fields."""

    def test_defaults(self):
        cfg = PipelineConfig()
        assert cfg.daily_buy_limit == 0  # unlimited
        assert cfg.enable_confidence_escalation is False

    def test_custom_values(self):
        cfg = PipelineConfig(daily_buy_limit=5, enable_confidence_escalation=True)
        assert cfg.daily_buy_limit == 5
        assert cfg.enable_confidence_escalation is True


class TestCheckDailyBuyAllowed:
    """FullPipelineBacktest._check_daily_buy_allowed() unit tests."""

    def _make_engine(self, limit: int = 5, escalation: bool = False):
        cfg = PipelineConfig(
            daily_buy_limit=limit,
            enable_confidence_escalation=escalation,
        )
        engine = FullPipelineBacktest(cfg)
        return engine

    def test_no_limit_always_allowed(self):
        engine = self._make_engine(limit=0)
        engine._daily_buy_count = 999
        assert engine._check_daily_buy_allowed(0.1) is True

    def test_hard_limit_under_limit(self):
        engine = self._make_engine(limit=5, escalation=False)
        engine._daily_buy_count = 3
        assert engine._check_daily_buy_allowed(0.3) is True

    def test_hard_limit_at_limit_blocks(self):
        engine = self._make_engine(limit=5, escalation=False)
        engine._daily_buy_count = 5
        assert engine._check_daily_buy_allowed(0.8) is False

    def test_hard_limit_at_limit_blocks_even_high_conf(self):
        """Without escalation, hard limit is absolute."""
        engine = self._make_engine(limit=5, escalation=False)
        engine._daily_buy_count = 5
        assert engine._check_daily_buy_allowed(0.95) is False

    def test_escalation_under_60pct_free(self):
        engine = self._make_engine(limit=10, escalation=True)
        engine._daily_buy_count = 5  # 50% usage
        assert engine._check_daily_buy_allowed(0.3) is True

    def test_escalation_at_60pct_needs_065(self):
        engine = self._make_engine(limit=10, escalation=True)
        engine._daily_buy_count = 6  # 60% usage
        assert engine._check_daily_buy_allowed(0.60) is False
        assert engine._check_daily_buy_allowed(0.65) is True

    def test_escalation_at_80pct_needs_075(self):
        engine = self._make_engine(limit=10, escalation=True)
        engine._daily_buy_count = 8  # 80% usage
        assert engine._check_daily_buy_allowed(0.70) is False
        assert engine._check_daily_buy_allowed(0.75) is True

    def test_escalation_over_limit_needs_090(self):
        engine = self._make_engine(limit=5, escalation=True)
        engine._daily_buy_count = 5  # at limit
        assert engine._check_daily_buy_allowed(0.85) is False
        assert engine._check_daily_buy_allowed(0.90) is True

    def test_escalation_at_100pct_allows_ultra_high(self):
        engine = self._make_engine(limit=5, escalation=True)
        engine._daily_buy_count = 7  # over limit
        assert engine._check_daily_buy_allowed(0.95) is True

    def test_escalation_boundary_values(self):
        """Test exact boundary values."""
        engine = self._make_engine(limit=5, escalation=True)

        # 2/5 = 40% → free
        engine._daily_buy_count = 2
        assert engine._check_daily_buy_allowed(0.01) is True

        # 3/5 = 60% → need 0.65
        engine._daily_buy_count = 3
        assert engine._check_daily_buy_allowed(0.64) is False
        assert engine._check_daily_buy_allowed(0.65) is True

        # 4/5 = 80% → need 0.75
        engine._daily_buy_count = 4
        assert engine._check_daily_buy_allowed(0.74) is False
        assert engine._check_daily_buy_allowed(0.75) is True

        # 5/5 = at limit → need 0.90
        engine._daily_buy_count = 5
        assert engine._check_daily_buy_allowed(0.89) is False
        assert engine._check_daily_buy_allowed(0.90) is True
