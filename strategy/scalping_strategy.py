import logging
import pandas as pd
from config import settings

logger = logging.getLogger(__name__)


class ScalpingStrategy:
    def __init__(self, risk_manager, technicals):
        self.risk_manager = risk_manager
        self.technicals = technicals

    @staticmethod
    def _is_extreme_mode(mode):
        return str(mode or "").strip().lower() == "flipping scalper"

    @staticmethod
    def _is_aggressive_mode(mode):
        return str(mode or "").strip().lower() == "aggressive scalper"

    @staticmethod
    def _is_steady_mode(mode):
        normalized = str(mode or "").strip().lower()
        return normalized in {"scalper", "steady", "steady scalper"}

    @staticmethod
    def _candle_is_green(row):
        return float(row["close"]) > float(row["open"])

    @staticmethod
    def _body_strength(row):
        candle_range = max(float(row["high"]) - float(row["low"]), 1e-9)
        return abs(float(row["close"]) - float(row["open"])) / candle_range

    @staticmethod
    def _upper_wick_ratio(row):
        candle_range = max(float(row["high"]) - float(row["low"]), 1e-9)
        upper_wick = float(row["high"]) - max(float(row["open"]), float(row["close"]))
        return max(0.0, upper_wick) / candle_range

    @staticmethod
    def _lower_wick_ratio(row):
        candle_range = max(float(row["high"]) - float(row["low"]), 1e-9)
        lower_wick = min(float(row["open"]), float(row["close"])) - float(row["low"])
        return max(0.0, lower_wick) / candle_range

    @staticmethod
    def _directional_efficiency(close_series):
        if len(close_series) < 2:
            return 0.0
        closes = [float(value) for value in close_series]
        net_move = closes[-1] - closes[0]
        path_distance = sum(abs(curr - prev) for prev, curr in zip(closes, closes[1:]))
        if path_distance <= 1e-9:
            return 0.0
        return net_move / path_distance

    @staticmethod
    def _higher_timeframe_trend_intact(tf_last, tf_prev):
        last_close = float(tf_last["close"])
        prev_close = float(tf_prev["close"])
        last_ema_9 = float(tf_last["ema_9"])
        prev_ema_9 = float(tf_prev["ema_9"])
        last_open = float(tf_last["open"])

        if last_close > prev_close:
            return True

        # Allow brief higher-timeframe pauses if trend structure is still intact
        # and the candle is holding near fast EMA support instead of rolling over.
        return (
            last_close >= last_ema_9 * 0.9985
            and last_close >= prev_ema_9 * 0.999
            and last_close >= last_open * 0.997
        )

    def _continuation_reclaim_ready(self, df, last_row, prev_row, short_high, mode="Scalper", manual_entry_override=False):
        close_price = float(last_row["close"])
        open_price = float(last_row["open"])
        ema_9 = float(last_row["ema_9"])
        ema_21 = float(last_row["ema_21"])
        vwap = float(last_row["vwap"])
        prev_close = float(prev_row["close"])
        prev_open = float(prev_row["open"])
        prev_ema_9 = float(prev_row["ema_9"])
        prev_vwap = float(prev_row["vwap"])
        prev_high = float(prev_row["high"])
        recent_window = df.tail(max(4, int(settings.ENTRY_LOOKBACK_CANDLES) + 1))
        recent_low = float(recent_window["low"].min())
        recent_high = float(recent_window["high"].max())
        pullback_window = df.tail(max(4, int(settings.ENTRY_LOOKBACK_CANDLES)))
        pullback_low = float(pullback_window["low"].min())
        pullback_close_low = float(pullback_window["close"].min())
        recovery_reference = float(pullback_window.tail(min(3, len(pullback_window)))["high"].max())
        pullback_midpoint = recent_low + ((recent_high - recent_low) * 0.5)
        recent_green_candles = int((pullback_window.tail(min(3, len(pullback_window)))["close"] > pullback_window.tail(min(3, len(pullback_window)))["open"]).sum())
        recent_advancing_closes = int((pullback_window.tail(min(4, len(pullback_window)))["close"].diff().fillna(0.0) > 0).sum())
        momentum_reclaim_reference = float(pullback_window.tail(min(4, len(pullback_window)))["high"].max())
        body_strength = self._body_strength(last_row)

        demand_zone_floor = min(
            prev_ema_9,
            prev_vwap,
            ema_9,
            vwap,
            float(pullback_window["ema_9"].min()),
            float(pullback_window["vwap"].min()),
        )
        retraced_to_support = (
            pullback_low <= (demand_zone_floor * 1.0035)
            or pullback_close_low <= (demand_zone_floor * 1.0025)
        )
        bullish_reclaim = (
            close_price > open_price
            and close_price >= ema_9 * 0.999
            and close_price >= vwap * 0.999
            and close_price >= max(prev_high * 0.9975, recovery_reference * 0.9975, momentum_reclaim_reference * 0.997)
        )
        structure_intact = (
            ema_9 >= ema_21
            and recent_high > recent_low
            and close_price >= max(pullback_midpoint * 0.999, recent_low + ((recent_high - recent_low) * 0.5))
            and close_price >= prev_close
        )
        not_overextended = close_price <= short_high * 1.0035
        continuation_pressure = (
            recent_green_candles >= 2
            and recent_advancing_closes >= 2
            and close_price >= float(pullback_window.iloc[-2]["close"]) * 1.0005
        )

        if self._is_extreme_mode(mode):
            not_overextended = close_price <= short_high * 1.007
        elif self._is_aggressive_mode(mode):
            not_overextended = close_price <= short_high * 1.0055

        if manual_entry_override:
            return retraced_to_support and bullish_reclaim and structure_intact

        return (
            retraced_to_support
            and bullish_reclaim
            and structure_intact
            and continuation_pressure
            and body_strength >= 0.12
            and not_overextended
            and not (prev_close < prev_open and close_price < prev_close)
        )

    def _trend_continuation_ready(self, df, last_row, prev_row, mode="Scalper", manual_entry_override=False):
        close_price = float(last_row["close"])
        open_price = float(last_row["open"])
        ema_9 = float(last_row["ema_9"])
        ema_21 = float(last_row["ema_21"])
        vwap = float(last_row["vwap"])
        macd = float(last_row["macd"])
        macd_signal = float(last_row["macd_signal"])
        rsi = float(last_row["rsi"])
        recent = df.tail(max(5, int(settings.ENTRY_LOOKBACK_CANDLES)))
        recent_low = float(recent["low"].min())
        recent_high = float(recent["high"].max())
        recent_mid = recent_low + ((recent_high - recent_low) * 0.5)
        last_four = recent.tail(min(4, len(recent)))
        green_count = int((last_four["close"] > last_four["open"]).sum())
        advancing_count = int((last_four["close"].diff().fillna(0.0) > 0).sum())
        body_strength = self._body_strength(last_row)
        directional_efficiency = self._directional_efficiency(recent["close"])

        if recent_high <= recent_low:
            return False

        pressure_ok = green_count >= 3 or (green_count >= 2 and advancing_count >= 2)
        trend_ok = (
            ema_9 >= ema_21
            and close_price >= ema_9 * 0.999
            and close_price >= vwap * 0.999
            and macd >= macd_signal * 0.997
            and rsi >= max(52.0, float(settings.RSI_BUY_MIN) - 2.0)
        )
        location_ok = (
            close_price >= recent_mid
            and close_price >= float(prev_row["high"]) * 0.996
            and close_price > open_price
        )
        momentum_ok = (
            body_strength >= 0.1
            and directional_efficiency >= max(0.18, float(settings.MOMENTUM_DIRECTIONAL_EFFICIENCY_MIN) * 0.45)
        )

        if self._is_extreme_mode(mode):
            location_ok = close_price >= recent_mid * 0.998 and close_price >= float(prev_row["high"]) * 0.994
        elif self._is_aggressive_mode(mode):
            location_ok = close_price >= recent_mid * 0.999 and close_price >= float(prev_row["high"]) * 0.995

        if manual_entry_override:
            return trend_ok and location_ok and pressure_ok

        return trend_ok and location_ok and pressure_ok and momentum_ok

    def _momentum_pump_ready(self, df, last_row, prev_row, orderbook_signal, mode="Scalper", adaptive_profile=None, manual_entry_override=False):
        adaptive_profile = adaptive_profile or {}
        if bool(adaptive_profile.get("strict_entries", False)) and not manual_entry_override:
            return False

        close_price = float(last_row["close"])
        open_price = float(last_row["open"])
        ema_9 = float(last_row["ema_9"])
        ema_21 = float(last_row["ema_21"])
        vwap = float(last_row["vwap"])
        macd = float(last_row["macd"])
        macd_signal = float(last_row["macd_signal"])
        macd_hist = float(last_row["macd_hist"])
        prev_macd_hist = float(prev_row["macd_hist"])
        rsi = float(last_row["rsi"])
        adx = float(last_row["adx"])
        volume_spike = float(last_row.get("volume_spike", 0.0) or 0.0)
        imbalance = float((orderbook_signal or {}).get("imbalance", 0.5) or 0.5)
        recent = df.tail(max(5, int(settings.ENTRY_LOOKBACK_CANDLES)))
        recent_base = float(recent.iloc[0]["close"])
        short_momentum = ((close_price - recent_base) / recent_base) if recent_base > 0 else 0.0
        green_count = int((recent.tail(min(3, len(recent)))["close"] > recent.tail(min(3, len(recent)))["open"]).sum())
        advancing_count = int((recent.tail(min(4, len(recent)))["close"].diff().fillna(0.0) > 0).sum())
        body_strength = self._body_strength(last_row)
        directional_efficiency = self._directional_efficiency(recent["close"])
        stretch_above_ema9_pct = ((close_price - ema_9) / ema_9) if ema_9 > 0 else 0.0

        max_stretch = 0.022
        if self._is_extreme_mode(mode):
            max_stretch = 0.03
        elif self._is_aggressive_mode(mode):
            max_stretch = 0.026

        return (
            close_price > open_price
            and ema_9 > ema_21
            and close_price >= vwap * 0.999
            and macd >= macd_signal * 0.998
            and macd_hist >= prev_macd_hist
            and rsi >= max(54.0, float(settings.RSI_BUY_MIN))
            and adx >= max(14.0, float(settings.REGIME_MIN_ADX) - 1.0)
            and volume_spike >= max(1.0, float(settings.VOLUME_SPIKE_FACTOR) * 0.75)
            and imbalance >= max(0.52, float(settings.BOOK_PRESSURE_THRESHOLD) - 0.03)
            and green_count >= 2
            and advancing_count >= 2
            and body_strength >= 0.18
            and directional_efficiency >= max(0.2, float(settings.MOMENTUM_DIRECTIONAL_EFFICIENCY_MIN) * 0.42)
            and short_momentum >= max(0.0045, float(settings.MIN_SHORT_MOMENTUM_PCT))
            and close_price >= float(prev_row["high"]) * 0.998
            and stretch_above_ema9_pct <= max_stretch
        )

    def _trend_structure_checks(self, df, last_row, prev_row, mode="Scalper", manual_entry_override=False):
        extreme_mode = self._is_extreme_mode(mode)
        aggressive_mode = self._is_aggressive_mode(mode)
        steady_mode = self._is_steady_mode(mode)
        lookback = max(4, int(settings.MOMENTUM_LOOKBACK_CANDLES))
        recent = df.tail(lookback)
        if len(recent) < lookback:
            return False, "Not enough recent candles for momentum structure"

        recent_start_close = float(recent.iloc[0]["close"])
        last_close = float(last_row["close"])
        if recent_start_close <= 0:
            return False, "Invalid recent close data"

        recent_gain = (last_close - recent_start_close) / recent_start_close
        if extreme_mode:
            min_recent_gain = settings.MOMENTUM_LOOKBACK_MIN_PCT * 0.65
        elif steady_mode:
            min_recent_gain = settings.MOMENTUM_LOOKBACK_MIN_PCT * 1.15
        elif aggressive_mode:
            min_recent_gain = settings.MOMENTUM_LOOKBACK_MIN_PCT * 0.9
        else:
            min_recent_gain = settings.MOMENTUM_LOOKBACK_MIN_PCT
        if manual_entry_override:
            min_recent_gain *= 0.55
        if recent_gain < min_recent_gain:
            return False, f"Recent momentum too weak ({recent_gain:.2%})"

        efficiency_floor = settings.MOMENTUM_DIRECTIONAL_EFFICIENCY_MIN
        if extreme_mode:
            efficiency_floor -= 0.14
        elif steady_mode:
            efficiency_floor += 0.08
        elif aggressive_mode:
            efficiency_floor -= 0.04
        directional_efficiency = self._directional_efficiency(recent["close"])
        if manual_entry_override:
            efficiency_floor -= 0.12
        if directional_efficiency < efficiency_floor:
            return False, f"Recent price action too choppy ({directional_efficiency:.2f})"

        recent_high = float(recent["high"].max())
        recent_low = float(recent["low"].min())
        if recent_high <= recent_low:
            return False, "Recent range is too compressed"
        range_position = (last_close - recent_low) / max(recent_high - recent_low, 1e-9)
        range_floor = settings.RECENT_RANGE_POSITION_MIN
        if extreme_mode:
            range_floor -= 0.10
        elif steady_mode:
            range_floor += 0.06
        elif aggressive_mode:
            range_floor -= 0.03
        if manual_entry_override:
            range_floor -= 0.12
        if range_position < range_floor:
            return False, "Close is too low in the recent range"

        lower_highs = sum(
            1 for previous_high, current_high in zip(recent["high"], recent["high"][1:])
            if float(current_high) < (float(previous_high) * (0.9995 if extreme_mode else 0.9998))
        )
        max_recent_lower_highs = settings.MAX_RECENT_LOWER_HIGHS + (1 if extreme_mode else 0)
        if manual_entry_override:
            max_recent_lower_highs += 2
        if lower_highs > max_recent_lower_highs:
            return False, "Recent highs are rolling over"

        min_adx = settings.MIN_ADX_TREND
        if extreme_mode:
            min_adx -= 3
        elif steady_mode:
            min_adx += 3
        elif aggressive_mode:
            min_adx -= 1
        if manual_entry_override:
            min_adx -= 5
        if float(last_row["adx"]) < min_adx:
            return False, f"Trend strength too weak (ADX {last_row['adx']:.2f})"

        min_fast_slope = settings.EMA_FAST_SLOPE_MIN
        if extreme_mode:
            min_fast_slope *= 0.5
        elif steady_mode:
            min_fast_slope *= 1.1
        elif aggressive_mode:
            min_fast_slope *= 0.85
        if manual_entry_override:
            min_fast_slope *= 0.65
        if float(last_row["ema_9_slope"]) < min_fast_slope:
            return False, "Fast EMA slope is not rising enough"
        min_slow_slope = settings.EMA_SLOW_SLOPE_MIN
        if extreme_mode:
            min_slow_slope -= 0.00005
        elif steady_mode:
            min_slow_slope += 0.00003
        if manual_entry_override:
            min_slow_slope -= 0.00005
        if float(last_row["ema_21_slope"]) < min_slow_slope:
            return False, "Slow EMA slope is turning down"

        if (
            not manual_entry_override
            and float(prev_row["close"]) < float(prev_row["ema_9"])
            and float(last_row["close"]) <= float(prev_row["high"])
        ):
            return False, "Pullback has not reclaimed prior candle high"

        return True, ""

    def _resistance_headroom_check(self, df, last_row, mode="Scalper", manual_entry_override=False):
        extreme_mode = self._is_extreme_mode(mode)
        aggressive_mode = self._is_aggressive_mode(mode)
        steady_mode = self._is_steady_mode(mode)
        lookback = max(8, int(settings.RESISTANCE_LOOKBACK_CANDLES))
        if len(df) <= lookback:
            return True, ""

        recent_slice = df.iloc[-lookback:-1]
        if recent_slice.empty:
            return True, ""

        left_resistance = float(recent_slice["high"].max())
        close_price = float(last_row["close"])
        current_high = float(last_row["high"])
        if left_resistance <= 0 or close_price <= 0:
            return True, ""

        distance_to_resistance = (left_resistance - close_price) / close_price
        near_threshold = settings.RESISTANCE_NEAR_THRESHOLD_PCT
        breakout_buffer = settings.RESISTANCE_BREAK_BUFFER
        if extreme_mode:
            near_threshold *= 1.35
            breakout_buffer -= 0.0004
        elif steady_mode:
            near_threshold *= 0.75
            breakout_buffer += 0.0005
        elif aggressive_mode:
            near_threshold *= 0.9

        if manual_entry_override:
            near_threshold *= 0.55
            breakout_buffer -= 0.0008

        if current_high >= left_resistance * breakout_buffer:
            return True, ""
        if 0 <= distance_to_resistance <= near_threshold:
            return False, f"Price is pressing into recent resistance ({distance_to_resistance:.2%} headroom)"
        return True, ""

    def _base_context_checks(self, last_row, prev_row, context, mode="Scalper", adaptive_profile=None):
        extreme_mode = self._is_extreme_mode(mode)
        aggressive_mode = self._is_aggressive_mode(mode)
        steady_mode = self._is_steady_mode(mode)
        adaptive_profile = adaptive_profile or {}
        strict_entries = bool(adaptive_profile.get("strict_entries", False))
        manual_entry_override = bool(context.get("manual_entry_override", False))
        day_gain = float(context.get("price_change_pct", 0.0) or 0.0)
        quote_volume = float(context.get("quote_volume", 0.0) or 0.0)
        safety_passed = bool(context.get("safety_passed", False))
        favorite_bypass_daily_gain = bool(context.get("favorite_bypass_daily_gain", False))

        if not safety_passed:
            return False, "Public safety filter not passed"
        min_daily_gain = settings.MIN_DAILY_GAIN
        max_daily_gain = settings.MAX_DAILY_GAIN_TO_CHASE
        min_quote_volume = settings.MIN_24H_QUOTE_VOLUME
        if extreme_mode:
            min_daily_gain *= 0.65
            max_daily_gain *= 1.35
            min_quote_volume *= 0.6
        elif steady_mode:
            min_daily_gain *= 0.85
            max_daily_gain *= 0.75
            min_quote_volume *= 1.2
        elif aggressive_mode:
            min_daily_gain *= 0.75
            max_daily_gain *= 1.05
            min_quote_volume *= 0.85
        if strict_entries and not manual_entry_override:
            min_quote_volume *= 1.25
        rsi_buy_min = settings.RSI_BUY_MIN
        if extreme_mode:
            rsi_buy_min -= 6
        elif steady_mode:
            rsi_buy_min += 2
        elif aggressive_mode:
            rsi_buy_min -= 2
        if strict_entries and not manual_entry_override:
            rsi_buy_min += settings.ADAPTIVE_RSI_FLOOR_BOOST
        if manual_entry_override:
            rsi_buy_min -= 12
        rsi_buy_max = settings.RSI_BUY_MAX
        if extreme_mode:
            rsi_buy_max += 4
        elif steady_mode:
            rsi_buy_max -= 6
        elif aggressive_mode:
            rsi_buy_max -= 1
        if manual_entry_override:
            rsi_buy_max += 6
        atr_min_pct = settings.ATR_MIN_PCT
        atr_max_pct = settings.ATR_MAX_PCT
        if extreme_mode:
            atr_min_pct *= 0.8
            atr_max_pct *= 1.2
        elif steady_mode:
            atr_max_pct *= 0.82
        elif aggressive_mode:
            atr_max_pct *= 0.95
        if strict_entries and not manual_entry_override:
            atr_max_pct *= 0.9
        if manual_entry_override:
            min_quote_volume *= 0.5
            atr_min_pct *= 0.7
            atr_max_pct *= 1.2

        if not favorite_bypass_daily_gain:
            if day_gain < min_daily_gain:
                return False, f"Daily gain too weak ({day_gain:.2f}%)"
            if day_gain > max_daily_gain:
                return False, f"Daily gain too extended ({day_gain:.2f}%)"
        if quote_volume < min_quote_volume:
            return False, "24h volume too low"
        if not (rsi_buy_min <= last_row["rsi"] <= rsi_buy_max):
            return False, f"RSI out of range ({last_row['rsi']:.2f})"
        if not extreme_mode and not manual_entry_override and last_row["rsi"] < prev_row["rsi"]:
            return False, "RSI momentum fading"
        if last_row["ema_9"] <= last_row["ema_21"]:
            return False, "EMA trend not bullish"
        if last_row["macd"] <= last_row["macd_signal"]:
            return False, "MACD momentum not improving"
        if not extreme_mode and not manual_entry_override and last_row["macd_hist"] <= prev_row["macd_hist"]:
            return False, "MACD momentum not improving"
        if extreme_mode:
            vwap_floor = 0.9965
        elif steady_mode:
            vwap_floor = 0.999
        elif aggressive_mode:
            vwap_floor = 0.9975
        else:
            vwap_floor = 0.998
        if strict_entries and not manual_entry_override:
            vwap_floor += 0.0005
        if manual_entry_override:
            vwap_floor -= 0.0015
        if last_row["close"] < (last_row["vwap"] * vwap_floor):
            return False, "Price below VWAP bias"
        min_close_to_ema9 = settings.MIN_CLOSE_TO_EMA9_RATIO
        if extreme_mode:
            min_close_to_ema9 -= 0.001
        elif steady_mode:
            min_close_to_ema9 += 0.0008
        elif aggressive_mode:
            min_close_to_ema9 += 0.0002
        if strict_entries and not manual_entry_override:
            min_close_to_ema9 += 0.0005
        if manual_entry_override:
            min_close_to_ema9 -= 0.0015
        if last_row["close"] < (last_row["ema_9"] * min_close_to_ema9):
            return False, "Price lost fast EMA support"

        atr_pct = (float(last_row["atr"]) / float(last_row["close"])) if float(last_row["close"]) > 0 else 0.0
        if atr_pct < atr_min_pct:
            return False, f"ATR too low ({atr_pct:.4f})"
        if atr_pct > atr_max_pct:
            return False, f"ATR too high ({atr_pct:.4f})"

        return True, ""

    def _regime_allows_entry(self, last_row, context):
        if not bool(context.get("safety_passed", False)):
            return False, "Public safety filter not passed"

        close_price = float(last_row["close"] or 0.0)
        atr_pct = (float(last_row["atr"]) / close_price) if close_price > 0 else 0.0
        quote_volume = float(context.get("quote_volume", 0.0) or 0.0)
        day_gain = float(context.get("price_change_pct", 0.0) or 0.0)

        if close_price <= 0:
            return False, "Invalid close price"
        if quote_volume < (settings.MIN_24H_QUOTE_VOLUME * 0.5):
            return False, "24h volume too low"
        if atr_pct < settings.ATR_MIN_PCT or atr_pct > settings.ATR_MAX_PCT:
            return False, f"ATR outside trading regime ({atr_pct:.4f})"
        if float(last_row["adx"]) < float(settings.REGIME_MIN_ADX):
            return False, f"Market too choppy (ADX {last_row['adx']:.2f})"
        if float(last_row["ema_9"]) <= float(last_row["ema_21"]):
            return False, "Trend bias not bullish"
        if close_price < float(last_row["vwap"]) * 0.997:
            return False, "Price below VWAP bias"
        if day_gain > (settings.MAX_DAILY_GAIN_TO_CHASE * 1.15):
            return False, f"Daily gain too extended ({day_gain:.2f}%)"
        return True, ""

    def _current_hour_manipulation_check(self, df):
        if df is None or len(df) < 12:
            return True, ""

        working = df.tail(120).copy()
        working["timestamp_dt"] = pd.to_datetime(working["timestamp"], unit="ms", utc=True)
        current_hour = working["timestamp_dt"].iloc[-1].floor("h")
        hour_window = working[working["timestamp_dt"].dt.floor("h") == current_hour]
        if len(hour_window) < 4:
            return True, ""

        hour_open = float(hour_window.iloc[0]["open"])
        hour_high = float(hour_window["high"].max())
        hour_low = float(hour_window["low"].min())
        hour_close = float(hour_window.iloc[-1]["close"])
        if hour_open <= 0 or hour_high <= 0 or hour_low <= 0:
            return True, ""

        hour_range_pct = (hour_high - hour_low) / hour_open
        retrace_from_high_pct = (hour_high - hour_close) / hour_high
        rebound_from_low_pct = (hour_close - hour_low) / hour_low

        manipulation_flags = 0
        if hour_range_pct >= float(settings.CURRENT_HOUR_MANIPULATION_RANGE_PCT):
            manipulation_flags += 1
        if retrace_from_high_pct >= float(settings.CURRENT_HOUR_MANIPULATION_RETRACE_PCT):
            manipulation_flags += 1
        if rebound_from_low_pct >= float(settings.CURRENT_HOUR_MANIPULATION_RETRACE_PCT):
            manipulation_flags += 1

        shock_candles = 0
        extreme_wicks = 0
        volume_bursts = 0
        for _, row in hour_window.iterrows():
            base_price = max(float(row["open"]), 1e-9)
            candle_range_pct = (float(row["high"]) - float(row["low"])) / base_price
            upper_wick_ratio = self._upper_wick_ratio(row)
            lower_wick_ratio = self._lower_wick_ratio(row)
            volume_spike = float(row.get("volume_spike", 0.0) or 0.0)

            if candle_range_pct >= float(settings.CURRENT_HOUR_MANIPULATION_CANDLE_PCT):
                shock_candles += 1
            if max(upper_wick_ratio, lower_wick_ratio) >= float(settings.CURRENT_HOUR_MANIPULATION_EXTREME_WICK_RATIO):
                extreme_wicks += 1
            if volume_spike >= float(settings.CURRENT_HOUR_MANIPULATION_VOLUME_SPIKE):
                volume_bursts += 1

        if shock_candles >= 2:
            manipulation_flags += 1
        if extreme_wicks >= 2:
            manipulation_flags += 1
        if volume_bursts >= 2:
            manipulation_flags += 1

        if manipulation_flags >= int(settings.CURRENT_HOUR_MANIPULATION_MIN_FLAGS):
            return False, (
                f"Current hour shows manipulation risk "
                f"({hour_range_pct:.2%} range, {retrace_from_high_pct:.2%} retrace)"
            )

        return True, ""

    def evaluate_buy(self, df, orderbook_signal, market_context=None, mode="Scalper", higher_timeframes=None, adaptive_profile=None):
        if len(df) < 30:
            return False, "Not enough data"

        context = market_context or {}
        adaptive_profile = adaptive_profile or {}
        manual_entry_override = bool(context.get("manual_entry_override", False))
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        prev2_row = df.iloc[-3]
        close_price = float(last_row["close"])
        current_high = float(last_row["high"])
        recent_base = float(df.iloc[-6]["close"]) if len(df) >= 6 else float(prev_row["close"])
        short_momentum = ((close_price - recent_base) / recent_base) if recent_base else 0.0
        last_three = df.tail(3)
        green_candles = sum(1 for _, row in last_three.iterrows() if self._candle_is_green(row))
        directional_efficiency = self._directional_efficiency(df.tail(max(4, int(settings.MOMENTUM_LOOKBACK_CANDLES)))["close"])
        body_strength = self._body_strength(last_row)
        upper_wick_ratio = self._upper_wick_ratio(last_row)
        momentum_pump_ready = self._momentum_pump_ready(
            df,
            last_row,
            prev_row,
            orderbook_signal,
            mode=mode,
            adaptive_profile=adaptive_profile,
            manual_entry_override=manual_entry_override,
        )
        permissive_momentum_bias = (
            momentum_pump_ready
            or self._trend_continuation_ready(
                df,
                last_row,
                prev_row,
                mode=mode,
                manual_entry_override=True,
            )
        ) and not bool(adaptive_profile.get("strict_entries", False))

        # Hard anti-chop guards: reject flat/tick-locked charts before score stacking.
        structural_window = df.tail(max(10, int(settings.BREAKOUT_LOOKBACK_CANDLES) * 2))
        struct_high = float(structural_window["high"].max())
        struct_low = float(structural_window["low"].min())
        struct_range_pct = ((struct_high - struct_low) / close_price) if close_price > 0 else 0.0
        unique_close_ratio = (
            float(structural_window["close"].nunique()) / float(len(structural_window))
            if len(structural_window) > 0
            else 0.0
        )
        min_tradeable_range_pct = float(settings.MIN_TRADEABLE_RANGE_PCT)
        if permissive_momentum_bias:
            min_tradeable_range_pct *= 0.55
        if struct_range_pct < min_tradeable_range_pct:
            return False, f"Range too flat ({struct_range_pct:.4%})"
        unique_close_floor = float(settings.MIN_UNIQUE_CLOSE_RATIO)
        if permissive_momentum_bias:
            unique_close_floor *= 0.55
        if unique_close_ratio < unique_close_floor:
            return False, f"Too many repeated prints ({unique_close_ratio:.2f})"

        short_window = df.tail(max(6, int(settings.BREAKOUT_LOOKBACK_CANDLES)))
        short_high = float(short_window["high"].max())
        short_low = float(short_window["low"].min())
        short_range_pct = ((short_high - short_low) / close_price) if close_price > 0 else 0.0
        if (
            not manual_entry_override
            and short_range_pct <= float(settings.SHORT_TF_SIDEWAYS_RANGE_MAX_PCT)
            and abs(directional_efficiency) <= float(settings.SHORT_TF_SIDEWAYS_EFFICIENCY_MAX)
            and not permissive_momentum_bias
        ):
            return False, f"Short timeframe is sideways ({short_range_pct:.3%} range)"

        previous_high = float(df.iloc[-2]["high"])
        stretch_above_ema9_pct = (
            (close_price - float(last_row["ema_9"])) / float(last_row["ema_9"])
            if float(last_row["ema_9"]) > 0
            else 0.0
        )
        if (
            not manual_entry_override
            and stretch_above_ema9_pct > float(settings.ENTRY_MAX_STRETCH_ABOVE_EMA9_PCT)
            and upper_wick_ratio > 0.24
            and not momentum_pump_ready
        ):
            return False, f"Entry too late after stretch ({stretch_above_ema9_pct:.2%} above EMA9)"
        breakout_confirmed = close_price >= max(previous_high, short_high) * float(settings.BREAKOUT_CONFIRMATION_BUFFER)
        continuation_reclaim = self._continuation_reclaim_ready(
            df,
            last_row,
            prev_row,
            short_high,
            mode=mode,
            manual_entry_override=manual_entry_override,
        )
        trend_continuation = self._trend_continuation_ready(
            df,
            last_row,
            prev_row,
            mode=mode,
            manual_entry_override=manual_entry_override,
        )
        if not manual_entry_override and not breakout_confirmed and not continuation_reclaim and not trend_continuation and not momentum_pump_ready and not permissive_momentum_bias:
            return False, "No breakout, reclaim, or trend continuation confirmation"

        regime_ok, regime_reason = self._regime_allows_entry(last_row, context)
        if not regime_ok and not manual_entry_override:
            return False, regime_reason

        manipulation_ok, manipulation_reason = self._current_hour_manipulation_check(df)
        if not manipulation_ok and not manual_entry_override:
            return False, manipulation_reason

        context_ok, context_reason = self._base_context_checks(
            last_row,
            prev_row,
            context,
            mode=mode,
            adaptive_profile=adaptive_profile,
        )
        if not context_ok:
            return False, context_reason

        structure_ok, structure_reason = self._trend_structure_checks(
            df,
            last_row,
            prev_row,
            mode=mode,
            manual_entry_override=manual_entry_override,
        )
        if not structure_ok:
            return False, structure_reason

        if (
            not manual_entry_override
            and close_price < float(prev_row["close"])
            and float(prev_row["close"]) < float(prev2_row["close"])
            and short_momentum < (settings.MIN_SHORT_MOMENTUM_PCT * 1.2)
        ):
            return False, "Momentum fading (two lower closes after setup)"

        if (
            not manual_entry_override
            and float(last_row["macd_hist"]) < float(prev_row["macd_hist"])
            and float(prev_row["macd_hist"]) < float(prev2_row["macd_hist"])
        ):
            return False, "Momentum histogram is rolling over"

        score = 0
        notes = []

        if float(last_row["ema_9"]) > float(last_row["ema_21"]):
            score += 2
        else:
            notes.append("EMA bias weak")

        if close_price >= float(last_row["vwap"]):
            score += 2
        else:
            notes.append("Below VWAP")

        if float(last_row["macd"]) >= float(last_row["macd_signal"]):
            score += 2
        else:
            notes.append("MACD weak")

        if settings.RSI_BUY_MIN <= float(last_row["rsi"]) <= settings.RSI_BUY_MAX:
            score += 1
        else:
            notes.append("RSI out of range")

        if float(last_row["rsi"]) >= float(prev_row["rsi"]):
            score += 1
        else:
            notes.append("RSI fading")

        if float(last_row["volume_spike"]) >= (settings.VOLUME_SPIKE_FACTOR * 0.9):
            score += 2
        else:
            notes.append("RVOL light")

        if short_momentum >= (settings.MIN_SHORT_MOMENTUM_PCT * 0.7):
            score += 2
        else:
            notes.append("Momentum light")

        if directional_efficiency >= max(0.22, settings.MOMENTUM_DIRECTIONAL_EFFICIENCY_MIN * 0.55):
            score += 1
        else:
            notes.append("Too choppy")

        if body_strength >= 0.18:
            score += 1
        if upper_wick_ratio <= (settings.BULLISH_WAVE_MAX_WICK_RATIO * 1.1):
            score += 1

        if float(last_row["adx"]) >= settings.MIN_ADX_TREND:
            score += 1
        elif float(last_row["adx"]) < settings.REGIME_MIN_ADX + 1:
            notes.append("Trend weak")

        if green_candles >= 2:
            score += 2
        if close_price > float(prev_row["high"]) * settings.PULLBACK_RECOVERY_BUFFER:
            score += 2
        elif close_price <= float(prev_row["close"]):
            notes.append("No continuation")

        recent_window = df.tail(max(2, int(settings.ENTRY_LOOKBACK_CANDLES)))
        recent_high = float(recent_window["high"].max())
        if recent_high > 0:
            pullback_from_high = (current_high - close_price) / close_price if close_price > 0 else 0.0
            if settings.ENTRY_PULLBACK_MIN <= pullback_from_high <= settings.MAX_PULLBACK_FROM_RECENT_HIGH_PCT:
                score += 1
            elif pullback_from_high < (settings.ENTRY_PULLBACK_MIN * 0.4):
                notes.append("Chasing live candle")

        signal = orderbook_signal if isinstance(orderbook_signal, dict) else {"imbalance": float(orderbook_signal or 0.5)}
        imbalance = float(signal.get("imbalance", 0.5) or 0.5)
        if imbalance >= settings.BOOK_PRESSURE_THRESHOLD:
            score += 1
        if signal.get("support_rising", False):
            score += 1
        if momentum_pump_ready:
            score += 2
            notes.append("Real-time momentum pump override")

        htf_points = 0
        for timeframe_df in (higher_timeframes or {}).values():
            if timeframe_df is None or len(timeframe_df) < 3:
                continue
            tf_last = timeframe_df.iloc[-1]
            if float(tf_last["ema_9"]) > float(tf_last["ema_21"]):
                htf_points += 1
            if float(tf_last["rsi"]) >= (settings.HTF_RSI_MIN - 2):
                htf_points += 1

        strong_ltf_points = 0
        if float(last_row["volume_spike"]) >= float(settings.STRONG_LTF_OVERRIDE_MIN_RVOL):
            strong_ltf_points += 1
        if short_momentum >= float(settings.STRONG_LTF_OVERRIDE_MIN_SHORT_MOMENTUM_PCT):
            strong_ltf_points += 1
        if directional_efficiency >= float(settings.STRONG_LTF_OVERRIDE_MIN_DIRECTIONAL_EFFICIENCY):
            strong_ltf_points += 1
        if body_strength >= float(settings.STRONG_LTF_OVERRIDE_MIN_BODY_STRENGTH):
            strong_ltf_points += 1
        if (
            close_price > float(prev_row["high"]) * settings.PULLBACK_RECOVERY_BUFFER
            and float(last_row["macd_hist"]) > float(prev_row["macd_hist"])
        ):
            strong_ltf_points += 1

        strong_ltf_override = strong_ltf_points >= int(settings.STRONG_LTF_OVERRIDE_MIN_POINTS)
        if not manual_entry_override and htf_points < int(settings.MIN_HTF_CONFIRM_POINTS):
            if not (
                strong_ltf_override
                and htf_points >= int(settings.MIN_HTF_CONFIRM_POINTS_FOR_LTF_OVERRIDE)
            ):
                return False, f"Higher timeframe confirmation too weak ({htf_points})"
            notes.append(f"LTF momentum-start override active ({strong_ltf_points}pts)")
        score += min(htf_points, 2)

        resistance_ok, resistance_reason = self._resistance_headroom_check(
            df,
            last_row,
            mode=mode,
            manual_entry_override=manual_entry_override,
        )
        if resistance_ok:
            score += 1
        else:
            notes.append(resistance_reason)

        threshold = int(settings.ENTRY_SCORE_THRESHOLD)
        normalized_mode = str(mode or "").strip().lower()
        if normalized_mode == "flipping scalper":
            threshold += 1
        elif normalized_mode in {"scalper", "steady", "steady scalper"}:
            threshold += 1
        threshold += max(0, int(adaptive_profile.get("entry_score_bonus", 0) or 0))
        if momentum_pump_ready and not bool((adaptive_profile or {}).get("strict_entries", False)):
            threshold = max(5, threshold - 2)
        if permissive_momentum_bias and not bool(adaptive_profile.get("strict_entries", False)):
            threshold = max(4, threshold - 3)
        if manual_entry_override:
            threshold = max(4, threshold - 2)

        if score >= threshold:
            return True, f"Score entry confirmed ({score}/{threshold})"

        detail = ", ".join(notes[:3]) if notes else "setup not strong enough"
        return False, f"Entry score too low ({score}/{threshold}): {detail}"
