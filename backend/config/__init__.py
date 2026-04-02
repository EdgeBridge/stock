"""Config package — re-exports all settings classes for backward compatibility.

Importing from ``config`` continues to work exactly as before::

    from config import AppConfig, KISConfig    # unchanged import path

New multi-account symbols are also available here::

    from config import AccountConfig, load_accounts
"""

from config.accounts import DEFAULT_ACCOUNT_ID, AccountConfig, load_accounts
from config.settings import (
    AppConfig,
    DatabaseConfig,
    ETFConfig,
    ExtendedHoursConfig,
    ExternalDataConfig,
    KISConfig,
    LLMConfig,
    NotificationConfig,
    RedisConfig,
    RiskConfig,
    TradingConfig,
)

__all__ = [
    # Legacy single-account settings (backward-compatible)
    "AppConfig",
    "DatabaseConfig",
    "ETFConfig",
    "ExtendedHoursConfig",
    "ExternalDataConfig",
    "KISConfig",
    "LLMConfig",
    "NotificationConfig",
    "RedisConfig",
    "RiskConfig",
    "TradingConfig",
    # Multi-account support (new in STOCK-82)
    "AccountConfig",
    "load_accounts",
    "DEFAULT_ACCOUNT_ID",
]
