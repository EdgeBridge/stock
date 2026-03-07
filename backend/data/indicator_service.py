"""Technical indicator computation service.

Uses pandas-ta to compute indicators on OHLCV DataFrames.
All indicators needed by strategies are centralized here.
"""

import logging

import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


class IndicatorService:
    """Compute technical indicators on OHLCV DataFrames."""

    @staticmethod
    def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Add all standard indicators used by strategies.

        Expects df with columns: open, high, low, close, volume.
        Returns df with additional indicator columns.
        """
        if df.empty or len(df) < 10:
            return df

        df = df.copy()

        # -- Moving Averages --
        df["ema_10"] = ta.ema(df["close"], length=10)
        df["ema_20"] = ta.ema(df["close"], length=20)
        df["ema_50"] = ta.ema(df["close"], length=50)
        if len(df) >= 200:
            df["ema_200"] = ta.ema(df["close"], length=200)
            df["sma_200"] = ta.sma(df["close"], length=200)
        df["sma_50"] = ta.sma(df["close"], length=50)

        # -- ADX --
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
        if adx_df is not None and not adx_df.empty:
            df["adx"] = adx_df.iloc[:, 0]       # ADX_14
            df["plus_di"] = adx_df.iloc[:, 1]   # DMP_14
            df["minus_di"] = adx_df.iloc[:, 2]  # DMN_14

        # -- RSI --
        df["rsi"] = ta.rsi(df["close"], length=14)

        # -- MACD --
        macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            df["macd"] = macd_df.iloc[:, 0]
            df["macd_histogram"] = macd_df.iloc[:, 1]
            df["macd_signal"] = macd_df.iloc[:, 2]

        # -- Bollinger Bands --
        bb_df = ta.bbands(df["close"], length=20, std=2.0)
        if bb_df is not None and not bb_df.empty:
            df["bb_lower"] = bb_df.iloc[:, 0]
            df["bb_mid"] = bb_df.iloc[:, 1]
            df["bb_upper"] = bb_df.iloc[:, 2]
            df["bb_bandwidth"] = bb_df.iloc[:, 3] if bb_df.shape[1] > 3 else None
            df["bb_pct"] = bb_df.iloc[:, 4] if bb_df.shape[1] > 4 else None

        # -- ATR --
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)

        # -- Volume --
        vol_sma = ta.sma(df["volume"], length=20)
        df["volume_sma_20"] = vol_sma
        if vol_sma is not None:
            df["volume_ratio"] = df["volume"] / vol_sma.replace(0, float("nan"))

        # -- OBV --
        df["obv"] = ta.obv(df["close"], df["volume"])

        # -- Stochastic RSI --
        stoch_rsi = ta.stochrsi(df["close"], length=14)
        if stoch_rsi is not None and not stoch_rsi.empty:
            df["stoch_rsi_k"] = stoch_rsi.iloc[:, 0]
            df["stoch_rsi_d"] = stoch_rsi.iloc[:, 1]

        # -- Supertrend --
        st_df = ta.supertrend(df["high"], df["low"], df["close"], length=10, multiplier=3.0)
        if st_df is not None and not st_df.empty:
            df["supertrend"] = st_df.iloc[:, 0]
            df["supertrend_direction"] = st_df.iloc[:, 1]

        # -- Donchian Channel --
        dc_df = ta.donchian(df["high"], df["low"], lower_length=20, upper_length=20)
        if dc_df is not None and not dc_df.empty:
            df["donchian_lower"] = dc_df.iloc[:, 0]
            df["donchian_mid"] = dc_df.iloc[:, 1]
            df["donchian_upper"] = dc_df.iloc[:, 2]

        # -- Rate of Change --
        df["roc_5"] = ta.roc(df["close"], length=5)
        df["roc_10"] = ta.roc(df["close"], length=10)
        df["roc_20"] = ta.roc(df["close"], length=20)

        # -- Keltner Channel (for squeeze detection) --
        kc_df = ta.kc(df["high"], df["low"], df["close"], length=20, scalar=1.5)
        if kc_df is not None and not kc_df.empty:
            df["kc_lower"] = kc_df.iloc[:, 0]
            df["kc_mid"] = kc_df.iloc[:, 1]
            df["kc_upper"] = kc_df.iloc[:, 2]

        return df

    @staticmethod
    def detect_ema_alignment(df: pd.DataFrame) -> str:
        """Detect EMA alignment pattern from latest row.

        Returns: PERFECT_BULL, PARTIAL_BULL, MIXED, PARTIAL_BEAR, PERFECT_BEAR
        """
        if df.empty:
            return "MIXED"

        row = df.iloc[-1]
        price = row["close"]
        ema10 = row.get("ema_10")
        ema20 = row.get("ema_20")
        ema50 = row.get("ema_50")
        ema200 = row.get("ema_200")

        if any(v is None or pd.isna(v) for v in [ema10, ema20, ema50]):
            return "MIXED"

        if ema200 is not None and not pd.isna(ema200):
            if price > ema10 > ema20 > ema50 > ema200:
                return "PERFECT_BULL"
            if price < ema10 < ema20 < ema50 < ema200:
                return "PERFECT_BEAR"

        if price > ema10 > ema20 > ema50:
            return "PARTIAL_BULL"
        if price < ema10 < ema20 < ema50:
            return "PARTIAL_BEAR"

        return "MIXED"

    @staticmethod
    def detect_squeeze(df: pd.DataFrame) -> bool:
        """Detect Bollinger Band squeeze (BB inside Keltner Channel)."""
        if df.empty:
            return False

        row = df.iloc[-1]
        bb_lower = row.get("bb_lower")
        bb_upper = row.get("bb_upper")
        kc_lower = row.get("kc_lower")
        kc_upper = row.get("kc_upper")

        if any(v is None or pd.isna(v) for v in [bb_lower, bb_upper, kc_lower, kc_upper]):
            return False

        return bb_lower > kc_lower and bb_upper < kc_upper
