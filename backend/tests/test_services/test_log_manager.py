"""Tests for the centralized structured logging system."""

import json
import logging
import os
import tempfile

import pytest

from services.log_manager import (
    ColoredFormatter,
    JSONFormatter,
    LogConfig,
    TradingLogger,
    get_trading_logger,
    setup_logging,
)


class TestLogConfig:
    def test_defaults(self):
        config = LogConfig()
        assert config.level == "INFO"
        assert config.log_dir == "logs"
        assert config.max_file_size_mb == 50
        assert config.backup_count == 5
        assert config.enable_file is True
        assert config.enable_json is True
        assert config.enable_console is True


class TestSetupLogging:
    def test_creates_handlers(self):
        """setup_logging should attach console, file, and JSON handlers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LogConfig(log_dir=tmpdir)
            setup_logging(config)

            root = logging.getLogger()
            handler_types = [type(h).__name__ for h in root.handlers]

            assert "StreamHandler" in handler_types
            assert handler_types.count("RotatingFileHandler") == 2

    def test_creates_log_directory(self):
        """setup_logging should create the logs directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "nested", "logs")
            config = LogConfig(log_dir=log_dir)
            setup_logging(config)

            assert os.path.isdir(log_dir)

    def test_console_only(self):
        """With file and JSON disabled, only a console handler is created."""
        config = LogConfig(enable_file=False, enable_json=False)
        setup_logging(config)

        root = logging.getLogger()
        handler_types = [type(h).__name__ for h in root.handlers]
        assert "StreamHandler" in handler_types
        assert "RotatingFileHandler" not in handler_types

    def test_log_level_is_applied(self):
        config = LogConfig(
            level="DEBUG", enable_file=False, enable_json=False
        )
        setup_logging(config)

        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_rotation_config(self):
        """File handlers should respect max size and backup count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LogConfig(
                log_dir=tmpdir, max_file_size_mb=10, backup_count=3
            )
            setup_logging(config)

            root = logging.getLogger()
            from logging.handlers import RotatingFileHandler

            rotating = [
                h for h in root.handlers
                if isinstance(h, RotatingFileHandler)
            ]
            assert len(rotating) == 2
            for h in rotating:
                assert h.maxBytes == 10 * 1024 * 1024
                assert h.backupCount == 3

    def test_clears_previous_handlers(self):
        """Calling setup_logging twice should not duplicate handlers."""
        config = LogConfig(enable_file=False, enable_json=False)
        setup_logging(config)
        count_first = len(logging.getLogger().handlers)

        setup_logging(config)
        count_second = len(logging.getLogger().handlers)

        assert count_first == count_second


class TestColoredFormatter:
    def test_does_not_crash(self):
        """Colored formatter should produce output without errors."""
        fmt = ColoredFormatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        record = logging.LogRecord(
            name="test", level=logging.WARNING,
            pathname="", lineno=0, msg="warning msg",
            args=(), exc_info=None,
        )
        output = fmt.format(record)
        assert "warning msg" in output
        # ANSI escape code should be present for WARNING
        assert "\033[33m" in output

    def test_preserves_original_levelname(self):
        """Formatting should not permanently mutate the record's levelname."""
        fmt = ColoredFormatter(fmt="%(levelname)s: %(message)s")
        record = logging.LogRecord(
            name="test", level=logging.ERROR,
            pathname="", lineno=0, msg="err",
            args=(), exc_info=None,
        )
        fmt.format(record)
        assert record.levelname == "ERROR"


class TestJSONFormatter:
    def test_produces_valid_json(self):
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="engine.risk", level=logging.WARNING,
            pathname="", lineno=0, msg="Limit hit",
            args=(), exc_info=None,
        )
        output = fmt.format(record)
        data = json.loads(output)

        assert data["level"] == "WARNING"
        assert data["logger"] == "engine.risk"
        assert data["message"] == "Limit hit"
        assert "timestamp" in data
        # ISO 8601 timestamp should contain 'T'
        assert "T" in data["timestamp"]

    def test_includes_extra_fields(self):
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="trade",
            args=(), exc_info=None,
        )
        record.symbol = "AAPL"
        record.price = 185.5
        output = fmt.format(record)
        data = json.loads(output)

        assert data["symbol"] == "AAPL"
        assert data["price"] == 185.5

    def test_includes_exception(self):
        fmt = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR,
            pathname="", lineno=0, msg="failed",
            args=(), exc_info=exc_info,
        )
        output = fmt.format(record)
        data = json.loads(output)

        assert "exception" in data
        assert "ValueError" in data["exception"]


class TestJSONFileOutput:
    def test_json_file_format(self):
        """Logs written via the JSON handler should be valid JSON lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LogConfig(
                log_dir=tmpdir,
                enable_file=False,
                enable_console=False,
                enable_json=True,
            )
            setup_logging(config)

            test_logger = logging.getLogger("test.json_output")
            test_logger.info("hello structured", extra={"order_id": "abc123"})

            # Flush handlers
            for h in logging.getLogger().handlers:
                h.flush()

            json_path = os.path.join(tmpdir, "trading.json")
            assert os.path.exists(json_path)

            with open(json_path) as f:
                lines = [l.strip() for l in f if l.strip()]

            assert len(lines) >= 1
            data = json.loads(lines[-1])
            assert data["message"] == "hello structured"
            assert data["order_id"] == "abc123"
            assert data["logger"] == "test.json_output"


class TestTradingLogger:
    def setup_method(self):
        """Capture log records for inspection."""
        self.records: list[logging.LogRecord] = []
        self.handler = logging.Handler()
        self.handler.emit = lambda record: self.records.append(record)
        # Ensure logger propagates and handler is installed
        logger = logging.getLogger("test.trading")
        logger.handlers.clear()
        logger.addHandler(self.handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        self.tlog = TradingLogger("test.trading")

    def teardown_method(self):
        logger = logging.getLogger("test.trading")
        logger.handlers.clear()
        logger.propagate = True

    def test_trade_method(self):
        self.tlog.trade("AAPL", "BUY", 10, 185.50, "momentum", order_id="X1")

        assert len(self.records) == 1
        rec = self.records[0]
        assert rec.levelno == logging.INFO
        assert rec.symbol == "AAPL"
        assert rec.side == "BUY"
        assert rec.qty == 10
        assert rec.price == 185.50
        assert rec.strategy == "momentum"
        assert rec.order_id == "X1"
        assert "TRADE" in rec.getMessage()

    def test_signal_method(self):
        self.tlog.signal("TSLA", "ENTRY", 0.87, "mean_reversion")

        rec = self.records[0]
        assert rec.levelno == logging.INFO
        assert rec.symbol == "TSLA"
        assert rec.signal_type == "ENTRY"
        assert rec.confidence == 0.87
        assert rec.strategy == "mean_reversion"

    def test_risk_method(self):
        self.tlog.risk("Daily loss limit hit", pnl=-500.0)

        rec = self.records[0]
        assert rec.levelno == logging.WARNING
        assert rec.pnl == -500.0
        assert "Daily loss limit hit" in rec.getMessage()

    def test_error_method(self):
        self.tlog.error("Order failed", order_id="Z9")

        rec = self.records[0]
        assert rec.levelno == logging.ERROR
        assert rec.order_id == "Z9"

    def test_error_with_exc_info(self):
        try:
            raise RuntimeError("api timeout")
        except RuntimeError as e:
            self.tlog.error("API call failed", exc_info=e)

        rec = self.records[0]
        assert rec.exc_info is not None

    def test_market_method(self):
        self.tlog.market("SPY gap up 1.5%", index="SPY", gap_pct=1.5)

        rec = self.records[0]
        assert rec.levelno == logging.INFO
        assert rec.context == "market"
        assert rec.index == "SPY"
        assert rec.gap_pct == 1.5


class TestGetTradingLogger:
    def test_factory_returns_trading_logger(self):
        tlog = get_trading_logger("my.module")
        assert isinstance(tlog, TradingLogger)
        assert tlog.logger.name == "my.module"

    def test_factory_returns_distinct_instances(self):
        a = get_trading_logger("mod.a")
        b = get_trading_logger("mod.b")
        assert a is not b
        assert a.logger.name != b.logger.name
