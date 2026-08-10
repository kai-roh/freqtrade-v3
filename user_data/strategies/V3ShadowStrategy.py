"""Fail-closed V3 shadow adapter.

This adapter intentionally emits no entries. A promoted deterministic policy
must replace the zero-signal boundary before shadow evaluation can begin.
"""

from freqtrade.strategy import IStrategy
from pandas import DataFrame


class V3ShadowStrategy(IStrategy):
    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "15m"
    startup_candle_count = 200
    process_only_new_candles = True
    stoploss = -0.03
    minimal_roi = {"0": 10.0}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = "v3_fail_closed"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        dataframe["exit_tag"] = None
        return dataframe

    def leverage(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        return 1.0
