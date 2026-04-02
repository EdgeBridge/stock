"""Multi-account configuration model and YAML/env loader.

Supports:
- accounts.yaml with multiple named accounts
- Backward-compatible fallback: single account from KIS_* environment variables
  → auto-creates default account with account_id="ACC001"
"""

import logging
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNT_ID = "ACC001"

# Supported market identifiers
MARKET_US = "US"
MARKET_KR = "KR"


class AccountConfig(BaseModel):
    """Configuration for a single KIS trading account.

    Fields map 1-to-1 with KIS API credentials.  ``markets`` controls which
    market engines are allowed to use this account.
    """

    account_id: str = Field(..., description="Unique account identifier (e.g. ACC001)")
    name: str = Field(default="", description="Human-readable account name")
    app_key: str = Field(default="", description="KIS API app key")
    app_secret: str = Field(default="", description="KIS API app secret")
    account_no: str = Field(default="", description="KIS account number (CANO)")
    account_product: str = Field(
        default="01", description="KIS account product code (ACNT_PRDT_CD)"
    )
    base_url: str = Field(
        default="https://openapivts.koreainvestment.com:29443",
        description="KIS API base URL (paper uses 'vts' domain; live uses openapi domain)",
    )
    ws_url: str = Field(
        default="ws://ops.koreainvestment.com:21000",
        description="KIS WebSocket URL for real-time market data",
    )
    markets: list[str] = Field(
        default_factory=lambda: [MARKET_US, MARKET_KR],
        description="Markets this account may trade: 'US', 'KR', or both",
    )

    @field_validator("markets")
    @classmethod
    def validate_markets(cls, v: list[str]) -> list[str]:
        """Reject unknown or empty market identifiers at load time."""
        allowed = {MARKET_US, MARKET_KR}
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"Unknown market identifier(s): {invalid}. Allowed: {allowed}")
        if not v:
            raise ValueError("markets must contain at least one market identifier")
        return v

    @property
    def is_paper(self) -> bool:
        """True when base_url points to the virtual trading service (VTS)."""
        return "vts" in self.base_url

    @property
    def is_live(self) -> bool:
        """True when base_url points to the live KIS production endpoint."""
        return not self.is_paper


def _account_from_env() -> AccountConfig:
    """Build the default ACC001 account from existing single-account env vars.

    Reads the same ``KIS_*`` prefixed variables used by ``KISConfig`` so that
    deployments that only set environment variables continue to work without
    any configuration changes.
    """
    return AccountConfig(
        account_id=DEFAULT_ACCOUNT_ID,
        name="Default Account",
        app_key=os.getenv("KIS_APP_KEY", ""),
        app_secret=os.getenv("KIS_APP_SECRET", ""),
        account_no=os.getenv("KIS_ACCOUNT_NO", ""),
        account_product=os.getenv("KIS_ACCOUNT_PRODUCT", "01"),
        base_url=os.getenv(
            "KIS_BASE_URL",
            "https://openapivts.koreainvestment.com:29443",
        ),
        ws_url=os.getenv("KIS_WS_URL", "ws://ops.koreainvestment.com:21000"),
        markets=[MARKET_US, MARKET_KR],
    )


def load_accounts(config_path: Optional[Path] = None) -> list[AccountConfig]:
    """Load account configurations from ``accounts.yaml`` or env vars.

    Resolution order:
    1. ``config_path`` if provided
    2. ``<project_root>/config/accounts.yaml`` (next to strategies.yaml)
    3. Fallback: single ACC001 account built from ``KIS_*`` environment variables

    Args:
        config_path: Explicit path to an accounts YAML file.  Defaults to
                     ``config/accounts.yaml`` relative to the project root.

    Returns:
        A non-empty list of :class:`AccountConfig` objects.  The list always
        contains at least one entry (the env-var fallback) so callers never
        have to guard against an empty list.

    Example accounts.yaml::

        accounts:
          - account_id: ACC001
            name: Main Paper Account
            app_key: "PSXXXXXXXXXX"
            app_secret: "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
            account_no: "12345678"
            account_product: "01"
            base_url: "https://openapivts.koreainvestment.com:29443"
            markets: [US, KR]
          - account_id: ACC002
            name: Live US Account
            app_key: "XXXXXXXXXX"
            app_secret: "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
            account_no: "87654321"
            account_product: "01"
            base_url: "https://openapi.koreainvestment.com:9443"
            markets: [US]
    """
    import yaml  # local import to keep startup fast when YAML is not needed

    if config_path is None:
        # Locate project root: backend/config/accounts.py -> backend/ -> project root
        config_path = Path(__file__).parent.parent.parent / "config" / "accounts.yaml"

    if config_path.exists():
        try:
            # Synchronous file I/O is intentional: load_accounts() is called only
            # during application startup (AdapterRegistry.__init__), before the
            # async event loop begins accepting requests.  The file is tiny
            # (typically < 1 KB) so blocking time is negligible.
            with open(config_path) as fh:
                data = yaml.safe_load(fh)
            accounts_data = (data or {}).get("accounts", [])
            if accounts_data:
                accounts: list[AccountConfig] = []
                parse_errors: list[tuple[str, Exception]] = []
                for acc in accounts_data:
                    try:
                        accounts.append(AccountConfig(**acc))
                    except Exception as exc:
                        aid = (
                            acc.get("account_id", "<unknown>")
                            if isinstance(acc, dict)
                            else repr(acc)
                        )
                        parse_errors.append((aid, exc))
                if parse_errors:
                    logger.warning(
                        "Skipped %d malformed account(s) in %s: %s",
                        len(parse_errors),
                        config_path,
                        [(aid, str(e)) for aid, e in parse_errors],
                    )
                if accounts:
                    logger.info("Loaded %d account(s) from %s", len(accounts), config_path)
                    return accounts
                logger.warning("accounts.yaml contains no valid accounts — using env vars")
            else:
                logger.warning("accounts.yaml exists but contains no accounts — using env vars")
        except Exception as exc:
            logger.warning(
                "Failed to load accounts.yaml (%s): %s — falling back to env vars",
                config_path,
                exc,
            )

    # Backward-compat: build ACC001 from existing KIS_* env vars
    account = _account_from_env()
    masked_key = (account.app_key[:4] + "****") if len(account.app_key) > 4 else "****"
    logger.info(
        "Using single account from env vars: %s (app_key prefix=%s)",
        account.account_id,
        masked_key,
    )
    return [account]
