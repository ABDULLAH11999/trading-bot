import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import uvicorn

from api_server import app, register_bot_manager
from bot_manager import MultiUserBotManager
from bot_state import BotState, Trade, set_current_state, state
from config import settings
from data.market_discovery import MarketDiscovery
from data.market_stream import MarketStream
from exchange.binance_client import BinanceClient
from execution.trade_executor import TradeExecutor
from indicators.technicals import TechnicalIndicators
from risk.risk_manager import RiskManager
from security.hardening import scan_workspace_security_issues
from strategy.scalping_strategy import ScalpingStrategy
from user_profiles import get_profile

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "trading.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class ScalperBot:
    def __init__(self, user_email=""):
        self.user_email = (user_email or "").strip().lower()
        self.state = BotState(user_email=self.user_email)
        set_current_state(self.state)
        if self._should_boot_from_env_default():
            state.account_mode = settings.DEFAULT_ACCOUNT_MODE
            state.is_paper_trading = state.account_mode == "test"
        state.account_mode = self._resolve_account_mode()
        self.exchange = self._build_exchange_client(state.account_mode, user_email=self.user_email)
        self.market_discovery = MarketDiscovery(settings)
        self.risk_manager = RiskManager(settings)
        self.technicals = TechnicalIndicators()
        self.strategy = ScalpingStrategy(self.risk_manager, self.technicals)
        self.executor = TradeExecutor(self.exchange)
        self.market_data = {}
        self.orderbook_data = {}
        self.market_context = {}
        self.active_trades = {}
        self.trading_symbols = list(settings.TRADING_SYMBOLS)
        self.last_entry_time = 0.0
        self.last_universe_refresh = 0.0
        self.closing_symbols = set()
        self.entry_symbols = set()
        self.next_close_attempt = {}
        self.close_failures = {}
        self.entry_confirmations = {}
        self.entry_rejection_log = {}
        self.stream = None
        self.loss_streak = 0
        self.circuit_breaker_until = 0.0
        self.session_starting_balance = 0.0
        self.last_stream_message_at = time.time()
        self.adaptive_state_label = None
        self._last_time_slot_active = None
        self.manual_close_wait_logged_at = {}
        self.session_anchor_timestamp = 0.0
        self.session_anchor_day = None
        self.session_peak_equity = 0.0
        self.session_target_armed = False
        self.session_mode_override = None
        self.ready_event = asyncio.Event()
        self.startup_error = None
        runtime_summary = settings.runtime_config_summary(state.account_mode, user_email=self.user_email)
        logger.info(
            "Runtime config loaded from %s | default=%s | selected=%s | key=%s",
            runtime_summary["env_file"],
            runtime_summary["default_account_mode"],
            runtime_summary["selected_account_mode"],
            runtime_summary["api_key_masked"],
        )

    def _load_user_preferences(self):
        profile = get_profile(self.user_email)
        favorite_pairs = []
        seen_pairs = set()
        for symbol in (profile.get("favorite_pairs") or []):
            normalized = str(symbol or "").strip().upper()
            if not normalized or normalized in seen_pairs:
                continue
            seen_pairs.add(normalized)
            favorite_pairs.append(normalized)
        time_slots = []
        seen_slots = set()
        for slot in (profile.get("time_slots") or []):
            if not isinstance(slot, dict):
                continue
            start_text = str(slot.get("start") or "").strip()
            end_text = str(slot.get("end") or "").strip()
            if not start_text or not end_text:
                continue
            slot_key = (start_text, end_text)
            if slot_key in seen_slots:
                continue
            seen_slots.add(slot_key)
            time_slots.append({"start": start_text, "end": end_text})
        return {
            "favorite_pairs_enabled": bool(profile.get("favorite_pairs_enabled", False)),
            "favorite_pairs": favorite_pairs,
            "time_slots_enabled": bool(profile.get("time_slots_enabled", False)),
            "time_slots": time_slots,
        }

    @staticmethod
    def _slot_to_minutes(value):
        text = str(value or "").strip()
        parts = text.split(":")
        if len(parts) != 2:
            return None
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError:
            return None
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None
        return hour * 60 + minute

    def _time_slot_is_open(self, now=None):
        if not state.time_slots_enabled:
            return True

        slots = state.time_slots or []
        if not slots:
            return False

        local_now = now or datetime.now().astimezone()
        current_minutes = (local_now.hour * 60) + local_now.minute
        for slot in slots:
            start_minutes = self._slot_to_minutes(slot.get("start"))
            end_minutes = self._slot_to_minutes(slot.get("end"))
            if start_minutes is None or end_minutes is None or start_minutes == end_minutes:
                continue
            if start_minutes < end_minutes:
                if start_minutes <= current_minutes < end_minutes:
                    return True
            elif current_minutes >= start_minutes or current_minutes < end_minutes:
                return True
        return False

    def _apply_time_slot_gate(self, force_log=False):
        if not state.time_slots_enabled:
            self._last_time_slot_active = None
            return

        slot_open = self._time_slot_is_open()
        if slot_open:
            state.set_activity("Time slot active. Waiting for spot momentum signals...")
        else:
            state.set_activity("Outside configured time slots. Trading paused.")

        if state.bot_enabled != slot_open:
            state.bot_enabled = slot_open
            if slot_open:
                state.add_log("Time-slot trading window opened. Bot trading ENABLED.")
            else:
                state.add_log("Time-slot trading window closed. Bot trading DISABLED.")
            state.save_state()
        elif force_log and self._last_time_slot_active is None:
            if slot_open:
                state.add_log("Time-slot trading is enabled and currently inside an active slot.")
            else:
                state.add_log("Time-slot trading is enabled but currently outside configured slots.")

        self._last_time_slot_active = slot_open

    async def apply_user_preferences(self, preferences=None, log_change=False, refresh=False):
        set_current_state(self.state)
        normalized_preferences = preferences or self._load_user_preferences()
        previous_enabled = bool(state.favorite_pairs_enabled)
        previous_pairs = list(state.favorite_pairs)
        previous_slots_enabled = bool(state.time_slots_enabled)
        previous_slots = list(state.time_slots)
        favorite_pairs = []
        seen_pairs = set()
        for symbol in (normalized_preferences.get("favorite_pairs") or []):
            normalized_symbol = str(symbol or "").strip().upper()
            if not normalized_symbol or normalized_symbol in seen_pairs:
                continue
            seen_pairs.add(normalized_symbol)
            favorite_pairs.append(normalized_symbol)

        if "favorite_pairs_enabled" in normalized_preferences:
            state.favorite_pairs_enabled = bool(normalized_preferences.get("favorite_pairs_enabled", False))
        state.favorite_pairs = favorite_pairs
        if "time_slots_enabled" in normalized_preferences:
            state.time_slots_enabled = bool(normalized_preferences.get("time_slots_enabled", False))
        normalized_slots = []
        seen_slots = set()
        if "time_slots" in normalized_preferences:
            for slot in (normalized_preferences.get("time_slots") or []):
                if not isinstance(slot, dict):
                    continue
                start_text = str(slot.get("start") or "").strip()
                end_text = str(slot.get("end") or "").strip()
                if not start_text or not end_text:
                    continue
                slot_key = (start_text, end_text)
                if slot_key in seen_slots:
                    continue
                seen_slots.add(slot_key)
                normalized_slots.append({"start": start_text, "end": end_text})
            state.time_slots = normalized_slots

        self._apply_time_slot_gate(force_log=log_change)
        state.save_state()

        if log_change:
            if state.favorite_pairs_enabled:
                if state.favorite_pairs:
                    state.add_log(f"Favorite pairs enabled. Bot will include: {', '.join(state.favorite_pairs[:10])}")
                else:
                    state.add_log("Favorite pairs enabled, but no favorite pairs are selected yet.")
            elif previous_enabled:
                state.add_log("Favorite pair filter disabled. Bot returned to normal market discovery flow.")

            if previous_pairs != state.favorite_pairs and state.favorite_pairs:
                state.add_log(f"Favorite pair list updated: {', '.join(state.favorite_pairs[:10])}")
            if previous_slots_enabled != state.time_slots_enabled:
                if state.time_slots_enabled:
                    state.add_log("Time-slot trading enabled. Bot will auto-enable/disable by your configured slots.")
                else:
                    state.add_log("Time-slot trading disabled. Manual bot enable/disable control restored.")
            if previous_slots != state.time_slots:
                if state.time_slots:
                    first_slots = ", ".join([f"{slot['start']}-{slot['end']}" for slot in state.time_slots[:6]])
                    state.add_log(f"Trading time slots updated: {first_slots}")
                else:
                    state.add_log("Trading time slots cleared.")

        if refresh:
            await self.refresh_trading_universe(force=True)

        return {
            "favorite_pairs_enabled": state.favorite_pairs_enabled,
            "favorite_pairs": list(state.favorite_pairs),
            "time_slots_enabled": state.time_slots_enabled,
            "time_slots": list(state.time_slots),
        }

    async def get_pair_options(self):
        return await self.market_discovery.list_pair_options(
            major_symbols=settings.MAJOR_SPOT_SYMBOLS,
            limit=settings.FAVORITE_PAIR_OPTIONS_LIMIT,
        )

    def _effective_bot_mode(self):
        return str(self.session_mode_override or state.bot_mode or "").strip()

    def _effective_risk_percentage(self):
        return max(0.0, min(100.0, float(state.risk_percentage or 0.0)))

    def _is_extreme_mode(self):
        return self._effective_bot_mode().lower() == "flipping scalper"

    def _is_aggressive_mode(self):
        return self._effective_bot_mode().lower() == "aggressive scalper"

    def _is_steady_mode(self):
        normalized = self._effective_bot_mode().lower()
        return normalized in {"scalper", "steady", "steady scalper"}

    def _entry_confirmation_requirement(self, adaptive_profile=None):
        required = max(1, int(getattr(settings, "ENTRY_CONFIRMATIONS_REQUIRED", 1)))
        adaptive_profile = adaptive_profile or {}
        if self._is_extreme_mode():
            required = max(1, required - 1)
        elif self._is_aggressive_mode():
            required = max(1, required - 1)
        if self._is_small_account() and not bool(adaptive_profile.get("strict_entries", False)):
            required = max(1, required - 1)
        if self._is_steady_mode() and bool(adaptive_profile.get("strict_entries", False)):
            required += 1
        required += max(0, int(adaptive_profile.get("entry_confirmation_bonus", 0) or 0))
        return required

    @staticmethod
    def _entry_signal_strength(reason):
        text = str(reason or "").strip()
        if "Score entry confirmed" not in text:
            return None
        try:
            score_text = text.split("(", 1)[1].split(")", 1)[0]
            score_value, threshold_value = score_text.split("/", 1)
            score = int(score_value.strip())
            threshold = int(threshold_value.strip())
            return score - threshold
        except Exception:
            return None

    def _should_fast_track_entry(self, reason, candle_closed=False, adaptive_profile=None):
        adaptive_profile = adaptive_profile or {}
        signal_edge = self._entry_signal_strength(reason)
        if signal_edge is None:
            return False
        if signal_edge >= 3:
            return True
        if candle_closed and signal_edge >= 2:
            return True
        if self._is_extreme_mode() and signal_edge >= 2 and not bool(adaptive_profile.get("strict_entries", False)):
            return True
        if self._is_aggressive_mode() and signal_edge >= 2 and not bool(adaptive_profile.get("strict_entries", False)):
            return True
        return False

    def _log_entry_rejection(self, symbol, reason, throttle_seconds=90):
        if not symbol or not reason:
            return
        now = time.time()
        record = self.entry_rejection_log.get(symbol, {})
        last_reason = str(record.get("reason") or "")
        last_at = float(record.get("timestamp", 0.0) or 0.0)
        if last_reason == reason and (now - last_at) < throttle_seconds:
            return
        self.entry_rejection_log[symbol] = {
            "reason": reason,
            "timestamp": now,
        }
        state.add_log(f"Entry skipped for {symbol}: {reason}")

    def _cooldown_minutes_for_current_mode(self):
        base_cooldown = float(settings.COOLDOWN_MINUTES)
        if self._is_extreme_mode():
            base_cooldown = max(4.0, base_cooldown * 0.9)
        if self._is_aggressive_mode():
            base_cooldown = max(3.0, base_cooldown * 0.8)
        elif self._is_steady_mode():
            base_cooldown = max(6.0, base_cooldown * 1.3)
        if self._is_small_account():
            base_cooldown *= float(getattr(settings, "SMALL_ACCOUNT_COOLDOWN_MULTIPLIER", 1.0))
        return base_cooldown

    def _mode_trade_plan_overrides(self):
        if self._is_extreme_mode():
            return {
                "stop_mult": 0.72,
                "profit_mult": 0.7,
                "quick_profit_mult": 0.75,
                "time_decay_seconds": max(180, int(settings.TIME_DECAY_SECONDS * 0.45)),
                "max_hold_seconds": max(420, int(settings.MAX_POSITION_HOLD_SECONDS * 0.4)),
                "min_hold_seconds": max(45, int(settings.MIN_HOLD_SECONDS * 0.5)),
                "min_hold_after_entry_seconds": max(60, int(settings.MIN_HOLD_SECONDS_AFTER_ENTRY * 0.45)),
                "profit_protection_trigger": max(0.004, settings.PROFIT_PROTECTION_TRIGGER * 0.55),
                "profit_protection_floor": max(0.0015, settings.PROFIT_PROTECTION_FLOOR * 0.55),
                "runner_bearish_exit_min_profit": max(0.0015, settings.RUNNER_BEARISH_EXIT_MIN_PROFIT * 0.6),
                "runner_giveback_pct": settings.RUNNER_MAX_GIVEBACK_PCT,
            }
        if self._is_steady_mode():
            return {
                "stop_mult": 1.08,
                "profit_mult": 1.45,
                "quick_profit_mult": 0.95,
                "time_decay_seconds": max(settings.TIME_DECAY_SECONDS * 2, 1500),
                "max_hold_seconds": max(settings.MAX_POSITION_HOLD_SECONDS * 2.5, 5400),
                "min_hold_seconds": max(settings.MIN_HOLD_SECONDS * 2, 360),
                "min_hold_after_entry_seconds": max(settings.MIN_HOLD_SECONDS_AFTER_ENTRY * 2, 420),
                "profit_protection_trigger": settings.PROFIT_PROTECTION_TRIGGER * 1.2,
                "profit_protection_floor": settings.PROFIT_PROTECTION_FLOOR * 1.35,
                "runner_bearish_exit_min_profit": settings.RUNNER_BEARISH_EXIT_MIN_PROFIT * 1.35,
                "runner_giveback_pct": settings.RUNNER_MAX_GIVEBACK_PCT * 1.5,
            }
        if self._is_aggressive_mode():
            return {
                "stop_mult": 0.94,
                "profit_mult": 1.12,
                "quick_profit_mult": 1.2,
                "time_decay_seconds": max(360, int(settings.TIME_DECAY_SECONDS * 0.75)),
                "max_hold_seconds": max(900, int(settings.MAX_POSITION_HOLD_SECONDS * 1.25)),
                "min_hold_seconds": max(90, int(settings.MIN_HOLD_SECONDS * 0.85)),
                "min_hold_after_entry_seconds": max(120, int(settings.MIN_HOLD_SECONDS_AFTER_ENTRY * 0.8)),
                "profit_protection_trigger": settings.PROFIT_PROTECTION_TRIGGER * 0.95,
                "profit_protection_floor": settings.PROFIT_PROTECTION_FLOOR * 0.9,
                "runner_bearish_exit_min_profit": settings.RUNNER_BEARISH_EXIT_MIN_PROFIT,
                "runner_giveback_pct": settings.RUNNER_MAX_GIVEBACK_PCT * 0.9,
            }
        return {
            "stop_mult": 1.0,
            "profit_mult": 1.0,
            "quick_profit_mult": 1.0,
            "time_decay_seconds": settings.TIME_DECAY_SECONDS,
            "max_hold_seconds": settings.MAX_POSITION_HOLD_SECONDS,
            "min_hold_seconds": settings.MIN_HOLD_SECONDS,
            "min_hold_after_entry_seconds": settings.MIN_HOLD_SECONDS_AFTER_ENTRY,
            "profit_protection_trigger": settings.PROFIT_PROTECTION_TRIGGER,
            "profit_protection_floor": settings.PROFIT_PROTECTION_FLOOR,
            "runner_bearish_exit_min_profit": settings.RUNNER_BEARISH_EXIT_MIN_PROFIT,
            "runner_giveback_pct": settings.RUNNER_MAX_GIVEBACK_PCT,
        }

    def _current_equity(self):
        return float(state._current_equity())

    def _current_trading_day_key(self):
        local_now = datetime.now().astimezone()
        shifted = local_now - timedelta(hours=float(getattr(settings, "TRADING_DAY_START_HOUR_LOCAL", 8)))
        return shifted.strftime("%Y-%m-%d")

    def _reset_daily_runtime_controls(self):
        self.session_anchor_day = self._current_trading_day_key()
        self.session_anchor_timestamp = time.time()
        self.session_peak_equity = max(self._current_equity(), float(self.session_starting_balance or 0.0))
        self.session_target_armed = False
        self.session_mode_override = None

    def _refresh_daily_session_if_needed(self):
        day_key = self._current_trading_day_key()
        if self.session_anchor_day == day_key:
            return
        previous_mode_override = self.session_mode_override
        self._reset_daily_runtime_controls()
        if previous_mode_override:
            state.add_log(
                f"New trading day started (8:00 AM PKT boundary). Runtime mode reset from {previous_mode_override} to {state.bot_mode}."
            )
        else:
            state.add_log("New trading day started (8:00 AM PKT boundary). Runtime mode reset to the configured bot mode.")

    @staticmethod
    def _step_down_mode(mode_text):
        normalized = str(mode_text or "").strip().lower()
        if normalized == "flipping scalper":
            return "Aggressive Scalper"
        if normalized == "aggressive scalper":
            return "Steady"
        if normalized in {"steady", "steady scalper"}:
            return "Scalper"
        return "Scalper"

    def _activate_post_target_profile(self):
        effective_mode = self._effective_bot_mode()
        self.session_mode_override = self._step_down_mode(effective_mode)
        state.add_log(f"Session target reached (+{settings.SESSION_TARGET_PROFIT_PCT * 100:.0f}%). Runtime mode shifted to {self.session_mode_override}.")

    def _update_session_controls(self):
        self._refresh_daily_session_if_needed()
        current_equity = self._current_equity()
        if current_equity > self.session_peak_equity:
            self.session_peak_equity = current_equity

        baseline = max(float(self.session_starting_balance or 0.0), 0.0)
        if baseline <= 0:
            return

        peak_return_pct = (self.session_peak_equity - baseline) / baseline
        if (not self.session_target_armed) and peak_return_pct >= float(settings.SESSION_TARGET_PROFIT_PCT):
            self.session_target_armed = True
            self._activate_post_target_profile()

    def _should_boot_from_env_default(self):
        if not state.loaded_account_mode:
            return True
        return (
            not state.bot_enabled
            and not state.active_trades
            and state.account_mode == "test"
            and settings.DEFAULT_ACCOUNT_MODE == "real"
            and state.test_balance is None
        )

    def _resolve_account_mode(self, requested_mode=None):
        mode = str(requested_mode or state.account_mode or settings.DEFAULT_ACCOUNT_MODE).strip().lower()
        if mode not in {"test", "real"}:
            return settings.DEFAULT_ACCOUNT_MODE
        return mode

    def _build_exchange_client(self, account_mode=None, user_email=None):
        runtime_email = (user_email or self.user_email or "").strip().lower()
        credentials = settings.get_binance_credentials(
            self._resolve_account_mode(account_mode),
            user_email=runtime_email,
        )
        return BinanceClient(
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
            paper_trading=credentials["paper_trading"],
            account_mode=credentials["account_mode"],
        )

    def _validate_account_mode_credentials(self, account_mode, user_email=None):
        return

    async def _apply_account_mode(self, account_mode, user_email=None, log_change=True):
        set_current_state(self.state)
        selected_mode = self._resolve_account_mode(account_mode)
        runtime_email = (user_email or self.user_email or "").strip().lower()
        credential_summary = settings.get_binance_credentials(selected_mode, user_email=runtime_email)
        has_user_credentials = (
            credential_summary.get("credential_source") == "user"
            and bool(str(credential_summary.get("api_key") or "").strip())
            and bool(str(credential_summary.get("api_secret") or "").strip())
        )
        new_exchange = self._build_exchange_client(selected_mode, user_email=runtime_email)
        if not has_user_credentials:
            await new_exchange.close()
            new_exchange = BinanceClient(
                api_key="",
                api_secret="",
                paper_trading=selected_mode != "real",
                account_mode=selected_mode,
            )
            old_exchange = self.exchange
            self.exchange = new_exchange
            self.executor.exchange_client = self.exchange
            if old_exchange and old_exchange is not new_exchange:
                await old_exchange.close()

            state.switch_account_mode(selected_mode)
            state.quote_asset = settings.QUOTE_ASSET
            if selected_mode == "test":
                new_exchange.paper_mode_degraded = True
                baseline_balance = float(state.test_balance if state.test_balance is not None else 100.0)
                state.set_test_balance_baseline(baseline_balance)
                state.update_balance(baseline_balance)
                self.session_starting_balance = baseline_balance
                if log_change:
                    state.add_log("Test account selected. Save your test API keys before enabling the bot.")
                state.set_activity("Test mode ready. Save test API keys to enable trading.")
            else:
                state.test_balance = None
                state.update_balance(0.0)
                self.session_starting_balance = 0.0
                if log_change:
                    state.add_log("Real account selected. Save your real API keys before enabling the bot.")
                state.set_activity("Real mode ready. Save real API keys to enable trading.")
            self._reset_daily_runtime_controls()
            state.save_state()
            return {
                "account_mode": state.account_mode,
                "is_paper_trading": state.is_paper_trading,
                "balance": float(state.balance or 0.0),
                "credentials_missing": True,
            }

        try:
            balance = await new_exchange.fetch_balance(settings.QUOTE_ASSET)
        except Exception as exc:
            formatted_error = settings.format_binance_auth_error(
                exc,
                selected_mode,
                user_email=runtime_email,
            )
            if selected_mode == "test":
                new_exchange.paper_mode_degraded = True
                state.switch_account_mode("test")
                state.quote_asset = settings.QUOTE_ASSET
                baseline_balance = float(state.test_balance if state.test_balance is not None else 100.0)
                state.set_test_balance_baseline(baseline_balance)
                state.update_balance(baseline_balance)
                self.session_starting_balance = baseline_balance
                self._reset_daily_runtime_controls()

                old_exchange = self.exchange
                self.exchange = new_exchange
                self.executor.exchange_client = self.exchange
                if old_exchange and old_exchange is not new_exchange:
                    await old_exchange.close()

                state.add_log(
                    f"TEST account connection failed, so bot switched to local paper mode: {formatted_error}"
                )
                state.set_activity("Testnet unavailable. Running local paper mode.")
                state.save_state()
                return {
                    "account_mode": state.account_mode,
                    "is_paper_trading": state.is_paper_trading,
                    "balance": baseline_balance,
                    "degraded_paper_mode": True,
                }

            await new_exchange.close()
            state.add_log(f"{selected_mode.upper()} account connection failed: {formatted_error}")
            raise ValueError(f"Could not connect to the selected {selected_mode} account: {formatted_error}") from exc

        old_exchange = self.exchange
        self.exchange = new_exchange
        self.executor.exchange_client = self.exchange
        if old_exchange and old_exchange is not new_exchange:
            await old_exchange.close()

        state.switch_account_mode(selected_mode)
        state.quote_asset = settings.QUOTE_ASSET
        if selected_mode == "real":
            state.test_balance = None
        state.update_balance(balance)
        self.session_starting_balance = balance
        self._reset_daily_runtime_controls()

        if selected_mode == "real":
            if log_change:
                state.add_log("Real account selected. Simulated balance disabled.")
        elif log_change:
            state.add_log("Test account selected.")

        state.set_activity("Account mode updated. Waiting for spot momentum signals...")
        state.save_state()
        return {
            "account_mode": state.account_mode,
            "is_paper_trading": state.is_paper_trading,
            "balance": balance,
        }

    async def switch_account_mode(self, account_mode, user_email=None):
        set_current_state(self.state)
        selected_mode = self._resolve_account_mode(account_mode)
        if selected_mode == state.account_mode:
            return {
                "account_mode": state.account_mode,
                "is_paper_trading": state.is_paper_trading,
                "message": "Account mode is already active.",
            }

        if state.active_trades:
            raise ValueError("Close all active trades before switching account mode.")

        previous_enabled = bool(state.bot_enabled)
        state.bot_enabled = False
        state.manual_trade_trigger = False
        state.manual_close_flags = {}
        result = await self._apply_account_mode(selected_mode, user_email=user_email, log_change=True)
        missing_credentials = bool((result or {}).get("credentials_missing") or (result or {}).get("credentials_invalid"))
        if missing_credentials:
            state.bot_enabled = False
        elif not state.time_slots_enabled:
            state.bot_enabled = previous_enabled
        else:
            self._apply_time_slot_gate(force_log=False)
        state.add_log(f"Account mode switched to {selected_mode.upper()} keys.")
        state.save_state()
        return result

    def _latest_price(self, symbol):
        df = self.market_data.get(symbol)
        if df is not None and not df.empty:
            return float(df.iloc[-1]["close"])
        return None

    async def _latest_price_with_fallback(self, symbol):
        cached_price = self._latest_price(symbol)
        if cached_price is not None and cached_price > 0:
            return cached_price
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            ticker_price = float((ticker or {}).get("last") or (ticker or {}).get("close") or 0.0)
            if ticker_price > 0:
                return ticker_price
        except Exception:
            return None
        return None

    async def _warmup_symbol(self, symbol):
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, limit=500)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            if df.empty:
                return False
            df = self.technicals.calculate_indicators(df, settings)
            self.market_data[symbol] = df
            self.orderbook_data.setdefault(symbol, {"imbalance": 0.5, "support_rising": False})
            return True
        except Exception as exc:
            logger.warning("Warmup failed for %s: %s", symbol, exc)
            return False

    def _build_higher_timeframe_df(self, df, timeframe):
        if df is None or df.empty:
            return None

        working = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        working["timestamp"] = pd.to_datetime(working["timestamp"], unit="ms", utc=True)
        working = working.set_index("timestamp")
        aggregated = working.resample(timeframe).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()
        if aggregated.empty:
            return None
        aggregated = aggregated.reset_index()
        aggregated["timestamp"] = (aggregated["timestamp"].astype("int64") // 10**6)
        return self.technicals.calculate_indicators(aggregated.tail(200), settings)

    def _get_higher_timeframe_context(self, symbol):
        df = self.market_data.get(symbol)
        return {
            "5m": self._build_higher_timeframe_df(df, "5min"),
            "15m": self._build_higher_timeframe_df(df, "15min"),
        }

    def _trend_supports_patience(self, symbol, df, current_rsi, current_macd, current_signal, ema_fast, ema_slow):
        orderbook_signal = self.orderbook_data.get(symbol, {"imbalance": 0.5, "support_rising": False})
        higher_timeframes = self._get_higher_timeframe_context(symbol)

        if ema_fast <= ema_slow or current_macd < current_signal or current_rsi < 50:
            return False
        if float(df.iloc[-1]["close"]) < float(df.iloc[-1]["vwap"]) * 0.998:
            return False
        if float(orderbook_signal.get("imbalance", 0.5) or 0.5) < settings.BOOK_PRESSURE_THRESHOLD:
            return False

        for timeframe_df in higher_timeframes.values():
            if timeframe_df is None or len(timeframe_df) < 2:
                return False
            tf_last = timeframe_df.iloc[-1]
            if tf_last["ema_9"] <= tf_last["ema_21"] or tf_last["rsi"] < settings.HTF_RSI_MIN:
                return False

        return True

    def _should_check_intrabar_entry(self, df, current_price):
        if df is None or len(df) < 3:
            return False

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        last_close = float(last_row["close"])
        last_open = float(last_row["open"])
        prev_high = float(prev_row["high"])

        if last_close <= last_open:
            return False
        if current_price < (prev_high * settings.INTRABAR_BREAKOUT_BUFFER):
            return False
        if float(last_row["ema_9"]) <= float(last_row["ema_21"]):
            return False
        if last_close < float(last_row["vwap"]) * 0.999:
            return False
        if float(last_row["macd"]) < float(last_row["macd_signal"]) * 0.995:
            return False
        return True

    def _entry_quality_score(self, df, orderbook_signal, context):
        if df is None or df.empty:
            return float("-inf")

        last_row = df.iloc[-1]
        close_price = float(last_row["close"] or 0.0)
        if close_price <= 0:
            return float("-inf")

        recent_base = float(df.iloc[-6]["close"]) if len(df) >= 6 else float(df.iloc[-2]["close"])
        short_momentum = ((close_price - recent_base) / recent_base) if recent_base > 0 else 0.0
        volume_spike = float(last_row.get("volume_spike", 0.0) or 0.0)
        imbalance = float((orderbook_signal or {}).get("imbalance", 0.5) or 0.5)
        rsi = float(last_row.get("rsi", 50.0) or 50.0)
        day_gain = float((context or {}).get("price_change_pct", 0.0) or 0.0)
        return (
            (short_momentum * 1000.0)
            + (volume_spike * 1.8)
            + (imbalance * 2.5)
            + max(0.0, rsi - 50.0) * 0.04
            + max(0.0, day_gain) * 0.015
        )

    def _manual_force_trade_ready(self, df, orderbook_signal, context):
        if df is None or len(df) < 30:
            return False, "Not enough data for manual force setup"

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        close_price = float(last_row["close"] or 0.0)
        open_price = float(last_row["open"] or 0.0)
        ema_9 = float(last_row["ema_9"] or 0.0)
        ema_21 = float(last_row["ema_21"] or 0.0)
        vwap = float(last_row["vwap"] or 0.0)
        macd = float(last_row["macd"] or 0.0)
        macd_signal = float(last_row["macd_signal"] or 0.0)
        rsi = float(last_row.get("rsi", 50.0) or 50.0)
        adx = float(last_row.get("adx", 0.0) or 0.0)
        recent = df.tail(max(5, int(settings.ENTRY_LOOKBACK_CANDLES)))
        green_count = int((recent["close"] > recent["open"]).sum())
        advancing_count = int((recent["close"].diff().fillna(0.0) > 0).sum())
        body_strength = self.strategy._body_strength(last_row)
        score = self._entry_quality_score(df, orderbook_signal, context)
        continuation_ready = self.strategy._trend_continuation_ready(
            df,
            last_row,
            prev_row,
            mode=self._effective_bot_mode(),
            manual_entry_override=True,
        )
        reclaim_ready = self.strategy._continuation_reclaim_ready(
            df,
            last_row,
            prev_row,
            float(recent["high"].max()),
            mode=self._effective_bot_mode(),
            manual_entry_override=True,
        )

        if close_price <= 0:
            return False, "Invalid live price"
        if not bool(context.get("safety_passed", False)):
            return False, "Safety filter not passed"
        if ema_9 <= ema_21:
            return False, "Trend is not bullish enough for forced best trade"
        if close_price < vwap * 0.9975:
            return False, "Price is still below VWAP bias"
        if macd < (macd_signal * 0.995):
            return False, "MACD momentum is still weak"
        if rsi < max(49.0, float(settings.RSI_BUY_MIN) - 4.0):
            return False, f"RSI still too weak ({rsi:.2f})"
        if adx < max(12.0, float(settings.REGIME_MIN_ADX) - 4.0):
            return False, f"Trend strength still weak ({adx:.2f})"
        if green_count < 3 and advancing_count < 3 and close_price <= open_price:
            return False, "Recent candles do not show enough continuation pressure"
        if body_strength < 0.08 and close_price <= float(prev_row["high"]) * 0.998:
            return False, "Current continuation candle is too weak"
        if continuation_ready or reclaim_ready:
            return True, f"Manual force continuation confirmed (score {score:.2f})"
        if score >= 5.5:
            return True, f"Manual force best setup selected by quality score ({score:.2f})"
        return False, f"Best setup score still too weak ({score:.2f})"

    async def execute_manual_best_setup(self):
        set_current_state(self.state)
        if not self.ready_event.is_set():
            state.add_log("Manual best-setup waiting for bot warmup to finish.")
            try:
                await asyncio.wait_for(self.ready_event.wait(), timeout=20)
            except asyncio.TimeoutError:
                state.add_log("Manual best-setup skipped: bot is still warming market data.")
                return {"status": "skipped", "detail": "bot_not_ready"}
        if self.startup_error:
            state.add_log(f"Manual best-setup skipped: bot startup issue: {self.startup_error}")
            return {"status": "skipped", "detail": "bot_startup_error"}

        if self.active_trades:
            state.add_log("Manual best-setup skipped: close the current active trade first.")
            return {"status": "skipped", "detail": "active_trade_open"}
        if not state.bot_enabled:
            state.add_log("Manual best-setup skipped: bot trading is disabled.")
            return {"status": "skipped", "detail": "bot_disabled"}
        if self._circuit_breaker_active():
            state.add_log("Manual best-setup skipped: circuit breaker is active.")
            return {"status": "skipped", "detail": "circuit_breaker_active"}

        state.set_activity("Scanning for the best live setup...")
        await self.refresh_trading_universe(force=True)

        best_candidate = None
        now = time.time()

        for symbol in list(self.trading_symbols):
            df = self.market_data.get(symbol)
            if df is None or len(df) < 30:
                continue

            current_price = float(df.iloc[-1]["close"])
            can_trade, trade_gate_reason = self.risk_manager.check_new_trade_allowance(
                symbol,
                now,
                cooldown_minutes=self._cooldown_minutes_for_current_mode(),
                active_trade_count=len(self.active_trades),
            )
            if not can_trade:
                continue

            context = dict(self.market_context.get(symbol, {"symbol": symbol, "safety_passed": False}))
            context["manual_entry_override"] = True
            orderbook_signal = self.orderbook_data.get(symbol, {"imbalance": 0.5, "support_rising": False})
            higher_timeframes = self._get_higher_timeframe_context(symbol)
            adaptive_profile = self._adaptive_trade_profile(symbol=symbol)
            should_buy, reason = self.strategy.evaluate_buy(
                df,
                orderbook_signal,
                market_context=context,
                mode=self._effective_bot_mode(),
                higher_timeframes=higher_timeframes,
                adaptive_profile=adaptive_profile,
            )
            score = self._entry_quality_score(df, orderbook_signal, context)
            manual_force_ok, manual_force_reason = self._manual_force_trade_ready(
                df,
                orderbook_signal,
                context,
            )
            if not should_buy and not manual_force_ok:
                continue

            chosen_reason = reason if should_buy else manual_force_reason
            candidate = {
                "symbol": symbol,
                "df": df,
                "price": current_price,
                "reason": f"Manual best setup confirmed: {chosen_reason}",
                "context": context,
                "score": score,
                "gate_reason": trade_gate_reason,
                "strategy_confirmed": should_buy,
            }
            if best_candidate is None or candidate["score"] > best_candidate["score"]:
                best_candidate = candidate

        if best_candidate is None:
            state.set_activity("No strong live setup found yet.")
            state.add_log("Manual best-setup skipped: no strong live setup available right now.")
            return {"status": "skipped", "detail": "no_valid_setup"}

        state.add_log(
            f"Manual best-setup selected {best_candidate['symbol']} ({best_candidate['reason']})."
        )
        await self._try_open_trade(
            best_candidate["symbol"],
            best_candidate["df"],
            best_candidate["price"],
            best_candidate["reason"],
            best_candidate["context"],
        )
        return {"status": "triggered", "symbol": best_candidate["symbol"]}

    def _runner_hold_state(
        self,
        symbol,
        df,
        current_price,
        trade_info,
        current_rsi,
        current_macd,
        current_signal,
        ema_fast,
        ema_slow,
        peak_profit_percent,
        peak_retrace_percent,
        bearish_confirmed,
    ):
        orderbook_signal = self.orderbook_data.get(symbol, {"imbalance": 0.5, "support_rising": False})
        higher_timeframes = self._get_higher_timeframe_context(symbol)
        recent_window = df.tail(4)
        bullish_closes = int((recent_window["close"] >= recent_window["open"]).sum())
        advancing_closes = int((recent_window["close"].diff().fillna(0.0) > 0).sum())
        price_above_vwap = current_price >= float(df.iloc[-1]["vwap"]) * 0.999
        htf_support = 0

        for timeframe_df in higher_timeframes.values():
            if timeframe_df is None or len(timeframe_df) < 2:
                continue
            tf_last = timeframe_df.iloc[-1]
            if (
                float(tf_last["close"]) >= float(tf_last["ema_9"])
                and float(tf_last["ema_9"]) >= float(tf_last["ema_21"])
                and float(tf_last["rsi"]) >= settings.HTF_RSI_MIN
            ):
                htf_support += 1

        runner_active = (
            peak_profit_percent >= settings.RUNNER_MIN_PROFIT_PCT
            and peak_profit_percent < (
                float(trade_info.get("base_profit_target_pct", trade_info.get("profit_target_pct", settings.PROFIT_TARGET)))
                * settings.RUNNER_EXTENDED_TARGET_MULTIPLIER
            )
            and peak_retrace_percent <= self._mode_trade_plan_overrides()["runner_giveback_pct"]
            and current_price >= ema_fast
            and ema_fast >= ema_slow
            and current_macd >= (current_signal * 0.995)
            and current_rsi >= settings.RUNNER_RSI_FLOOR
            and price_above_vwap
            and bullish_closes >= 2
            and advancing_closes >= 2
            and float(orderbook_signal.get("imbalance", 0.5) or 0.5) >= settings.RUNNER_ORDERBOOK_IMBALANCE_MIN
            and htf_support >= 1
        )
        momentum_fading = (
            current_price < ema_fast
            or current_macd < current_signal
            or current_rsi < settings.RUNNER_RSI_FLOOR
            or bearish_confirmed
            or peak_retrace_percent > self._mode_trade_plan_overrides()["runner_giveback_pct"]
        )
        return {
            "runner_active": runner_active,
            "momentum_fading": momentum_fading,
            "htf_support": htf_support,
        }

    def _post_entry_structure_intact(self, df, trade_info, current_price, ema_fast, ema_slow, current_macd, current_signal):
        if df is None or df.empty:
            return False
        if current_price < float(trade_info["entry_price"]) * (1 - settings.POST_ENTRY_STRUCTURE_HOLD_MAX_PULLBACK_PCT):
            return False
        if current_price < ema_fast * 0.998:
            return False
        if ema_fast < ema_slow:
            return False
        if current_macd < current_signal * 0.992:
            return False

        recent = df.tail(4)
        bullish_closes = int((recent["close"] >= recent["open"]).sum())
        return bullish_closes >= 2

    def _current_available_balance(self):
        if state.test_balance is not None:
            return float(state.test_balance or 0.0)
        return float(state.balance or 0.0)

    def _is_small_account(self):
        return self._current_available_balance() <= float(settings.SMALL_ACCOUNT_EQUITY_THRESHOLD)

    def _adaptive_trade_profile(self, symbol=None):
        self._update_session_controls()
        small_account = self._is_small_account()
        strict_entries = bool(self.session_target_armed or self.session_mode_override or small_account)
        entry_confirmation_bonus = settings.ADAPTIVE_ENTRY_CONFIRMATION_BONUS if strict_entries else 0
        if small_account:
            entry_confirmation_bonus += int(getattr(settings, "SMALL_ACCOUNT_ENTRY_CONFIRMATION_BONUS", 0) or 0)
        return {
            "strict_entries": strict_entries,
            "entry_confirmation_bonus": entry_confirmation_bonus,
            "entry_score_bonus": 1 if strict_entries else 0,
            "min_peak_retrace_for_bearish_exit": settings.MIN_PEAK_RETRACE_FOR_BEARISH_EXIT,
        }

    def _clear_entry_confirmation(self, symbol):
        self.entry_confirmations.pop(symbol, None)
        self.entry_rejection_log.pop(symbol, None)

    async def get_chart_payload(self, symbol):
        normalized_symbol = str(symbol or "").strip().upper().replace("-", "/")
        if not normalized_symbol:
            return None

        if normalized_symbol not in self.market_data:
            warmed = await self._warmup_symbol(normalized_symbol)
            if not warmed:
                return None

        df = self.market_data.get(normalized_symbol)
        if df is None or df.empty:
            return None

        candles = []
        for _, row in df.tail(120).iterrows():
            candles.append({
                "timestamp": int(float(row["timestamp"]) / 1000.0),
                "open": round(float(row["open"]), 8),
                "high": round(float(row["high"]), 8),
                "low": round(float(row["low"]), 8),
                "close": round(float(row["close"]), 8),
            })

        trade = state.active_trades.get(normalized_symbol)
        if trade is None:
            for closed_trade in reversed(state.closed_trades):
                if closed_trade.symbol == normalized_symbol:
                    trade = closed_trade
                    break

        trade_payload = None
        if trade is not None:
            trade_payload = {
                "symbol": normalized_symbol,
                "status": str(getattr(trade, "status", "open") or "open"),
                "entry_price": round(float(getattr(trade, "entry_price", 0.0) or 0.0), 8),
                "stop_loss_price": round(float(getattr(trade, "stop_loss_price", 0.0) or 0.0), 8),
                "hard_stop_price": round(float(getattr(trade, "hard_stop_price", 0.0) or 0.0), 8),
                "profit_target_price": round(float(getattr(trade, "profit_target_price", 0.0) or 0.0), 8),
                "quick_profit_price": round(float(getattr(trade, "quick_profit_price", 0.0) or 0.0), 8),
                "high_water_price": round(float(getattr(trade, "high_water_price", getattr(trade, "entry_price", 0.0)) or 0.0), 8),
                "exit_price": round(float(getattr(trade, "exit_price", 0.0) or 0.0), 8),
                "opened_at": float(getattr(trade, "timestamp", 0.0) or 0.0),
                "closed_at": float(getattr(trade, "exit_timestamp", 0.0) or 0.0),
                "exit_reason": str(getattr(trade, "exit_reason", "") or ""),
                "pnl": round(float(getattr(trade, "pnl", 0.0) or 0.0), 8),
                "net_pnl": round(float(getattr(trade, "net_pnl", 0.0) or 0.0), 8),
            }

        return {
            "symbol": normalized_symbol,
            "candles": candles,
            "trade": trade_payload,
            "current_price": candles[-1]["close"] if candles else 0.0,
        }

    def _confirm_entry_signal(self, symbol, reason):
        now = time.time()
        record = self.entry_confirmations.get(symbol, {})
        last_seen = float(record.get("last_seen", 0.0) or 0.0)
        last_reason = record.get("reason")
        confirmations = int(record.get("count", 0) or 0)

        if (now - last_seen) > settings.ENTRY_CONFIRMATION_WINDOW_SECONDS or last_reason != reason:
            confirmations = 0

        confirmations += 1
        self.entry_confirmations[symbol] = {
            "count": confirmations,
            "last_seen": now,
            "reason": reason,
        }
        return confirmations

    def _circuit_breaker_active(self):
        now = time.time()
        if self.circuit_breaker_until <= now:
            return False
        return True

    def _maybe_trigger_circuit_breaker(self):
        balance_reference = max(self.session_starting_balance, 0.0)
        realized_drawdown = -min(state.total_pnl, 0.0)
        drawdown_limit = balance_reference * settings.CIRCUIT_BREAKER_DRAWDOWN_PCT
        streak_hit = self.loss_streak >= settings.LOSS_STREAK_LIMIT
        drawdown_hit = balance_reference > 0 and realized_drawdown >= drawdown_limit

        if not streak_hit and not drawdown_hit:
            return

        recorded_loss_streak = self.loss_streak
        self.circuit_breaker_until = time.time() + settings.CIRCUIT_BREAKER_COOLDOWN_SECONDS
        self.loss_streak = 0
        reasons = []
        if streak_hit:
            reasons.append(f"{recorded_loss_streak} consecutive losses")
        if drawdown_hit:
            reasons.append(f"{realized_drawdown:.2f} {settings.QUOTE_ASSET} drawdown")
        reason_text = " and ".join(reasons)
        if self._is_extreme_mode():
            reason_text = f"{reason_text} while in Flipping Scalper mode"
        state.add_log(
            f"Circuit breaker active for {settings.CIRCUIT_BREAKER_COOLDOWN_SECONDS // 60}m due to {reason_text}."
        )
        state.set_activity("Circuit breaker active. New entries paused.")

    def _record_trade_outcome(self, pnl):
        self._update_session_controls()
        if pnl < 0:
            self.loss_streak += 1
        else:
            self.loss_streak = 0
        self._maybe_trigger_circuit_breaker()

    async def refresh_trading_universe(self, force=False):
        now = time.time()
        if not force and (now - self.last_universe_refresh) < settings.UNIVERSE_REFRESH_SECONDS:
            return

        discovered_symbols = []
        discovered_context = {}
        try:
            candidates = await self.market_discovery.discover_candidates()
            for candidate in candidates:
                discovered_context[candidate["symbol"]] = candidate
                discovered_symbols.append(candidate["symbol"])
        except Exception as exc:
            logger.error("Market discovery failed: %s", exc)

        favorite_pairs_active = bool(state.favorite_pairs_enabled and state.favorite_pairs)
        selected_symbols = []
        new_context = {}
        if favorite_pairs_active:
            try:
                snapshot = await self.market_discovery.fetch_supported_spot_snapshot()
            except Exception as exc:
                logger.error("Favorite pair snapshot load failed: %s", exc)
                snapshot = {}

            for symbol in state.favorite_pairs:
                selected_symbols.append(symbol)
                favorite_snapshot = snapshot.get(symbol, {})
                base_context = dict(discovered_context.get(symbol, {}))
                base_context.update({
                    "symbol": symbol,
                    "favorite_bypass_daily_gain": True,
                    "is_favorite": True,
                    "safety_passed": bool(base_context.get("safety_passed", True)),
                    "price_change_pct": float(favorite_snapshot.get("price_change_pct", base_context.get("price_change_pct", 0.0)) or 0.0),
                    "quote_volume": float(favorite_snapshot.get("quote_volume", base_context.get("quote_volume", 0.0)) or 0.0),
                    "trade_count": int(favorite_snapshot.get("trade_count", base_context.get("trade_count", 0)) or 0),
                    "base_asset": favorite_snapshot.get("base_asset", base_context.get("base_asset", symbol.split("/")[0])),
                    "quote_asset": favorite_snapshot.get("quote_asset", base_context.get("quote_asset", settings.QUOTE_ASSET)),
                })
                new_context[symbol] = base_context
        else:
            selected_symbols = list(discovered_symbols)
            new_context = dict(discovered_context)

        if not selected_symbols:
            logger.warning("No dynamic candidates found. Falling back to configured symbols.")
            selected_symbols = list(settings.TRADING_SYMBOLS)

        for symbol in list(state.active_trades.keys()):
            if symbol not in selected_symbols:
                selected_symbols.append(symbol)

        ready_symbols = []
        for symbol in selected_symbols:
            if symbol in self.market_data or await self._warmup_symbol(symbol):
                ready_symbols.append(symbol)

        if ready_symbols:
            self.trading_symbols = ready_symbols
            self.market_context = {sym: new_context.get(sym, {"symbol": sym, "safety_passed": sym in new_context}) for sym in ready_symbols}
            if self.stream:
                self.stream.update_symbols(self.trading_symbols)

            tracked_text = ", ".join(self.trading_symbols[:6])
            if favorite_pairs_active:
                state.add_log(f"Tracking favorite pairs only: {tracked_text}")
            else:
                state.add_log(f"Tracking Binance spot movers: {tracked_text}")
            if favorite_pairs_active:
                state.add_log(f"Favorite pair bypass active for: {', '.join(state.favorite_pairs[:6])}")
            self.last_universe_refresh = now

    async def initialize(self):
        if settings.ENABLE_STARTUP_SECURITY_SCAN:
            security_findings = scan_workspace_security_issues(BASE_DIR)
            if security_findings:
                state.bot_enabled = False
                state.bot_running = False
                state.set_activity("Security block: suspicious native files detected.")
                state.add_log("Startup security scan detected suspicious files. Trading is blocked.")
                for finding in security_findings[:20]:
                    state.add_log(f"SECURITY ALERT: {finding}")
                state.save_state()
                raise RuntimeError("Startup blocked by workspace security scan findings.")

        logger.info("Initializing bot and refreshing Binance spot candidates...")
        state.set_activity("Scanning Binance spot listings and gainers...")
        state.save_state()
        if state.bot_enabled:
            state.add_log("Bot runtime restored with trading still enabled.")
        else:
            state.add_log("App started with bot trading disabled.")

        await self._apply_account_mode(state.account_mode, user_email=self.user_email, log_change=False)
        await self.apply_user_preferences(log_change=False, refresh=False)
        self._apply_time_slot_gate(force_log=True)

        if not state.is_paper_trading:
            state.add_log("Real/Live Mode detected: Disabling simulated balance.")
        else:
            state.add_log("Paper/Test Mode detected.")

        await self.refresh_trading_universe(force=True)

        for symbol, trade in state.active_trades.items():
            if symbol not in self.market_data:
                await self._warmup_symbol(symbol)

            self.active_trades[symbol] = {
                "entry_price": trade.entry_price,
                "stop_loss_price": trade.stop_loss_price,
                "amount": trade.amount,
                "timestamp": trade.timestamp,
                "high_water_price": float(trade.high_water_price or trade.entry_price),
                "hard_stop_price": float(getattr(trade, "hard_stop_price", 0.0) or (trade.entry_price * (1 - settings.HARD_STOP_LOSS))),
                "base_profit_target_pct": float(getattr(trade, "base_profit_target_pct", 0.0) or getattr(trade, "profit_target_pct", 0.0) or settings.PROFIT_TARGET),
                "profit_target_pct": float(getattr(trade, "profit_target_pct", 0.0) or settings.PROFIT_TARGET),
                "quick_profit_pct": float(getattr(trade, "quick_profit_pct", 0.0) or settings.QUICK_PROFIT_TARGET),
                "profit_target_price": float(getattr(trade, "profit_target_price", 0.0) or (trade.entry_price * (1 + float(getattr(trade, "profit_target_pct", 0.0) or settings.PROFIT_TARGET)))),
                "quick_profit_price": float(getattr(trade, "quick_profit_price", 0.0) or (trade.entry_price * (1 + float(getattr(trade, "quick_profit_pct", 0.0) or settings.QUICK_PROFIT_TARGET)))),
            }
            self.last_entry_time = max(self.last_entry_time, trade.timestamp)

        self.risk_manager.current_trades = len(self.active_trades)
        state.start_time = time.time()
        self._reset_daily_runtime_controls()
        state.set_activity("Bot ready. Waiting for spot momentum signals...")
        state.bot_running = True

    async def _force_close_trade(self, symbol, current_price, reason):
        if symbol not in self.active_trades or symbol in self.closing_symbols:
            return

        now = time.time()
        next_attempt = self.next_close_attempt.get(symbol, 0.0)
        if now < next_attempt:
            return

        self.closing_symbols.add(symbol)
        try:
            trade_info = self.active_trades[symbol]
            logger.info("== FORCE SELL: %s at %s. Reason: %s ==", symbol, current_price, reason)
            state.set_activity(f"Selling {symbol} at {current_price}...")
            state.add_log(f"SELL {symbol} @ {current_price} ({reason})")

            trade_amount = trade_info["amount"]
            try:
                base_asset = symbol.split("/")[0]
                if state.test_balance is not None:
                    available_base = float(trade_amount)
                else:
                    available_base = float(await self.exchange.fetch_balance(base_asset) or 0.0)
                if available_base > 0:
                    sell_amount = min(float(trade_amount), available_base)
                    if sell_amount < float(trade_amount):
                        state.add_log(
                            f"Adjusted sell size for {symbol} from {trade_amount:.8f} to Binance free balance {sell_amount:.8f} {base_asset}."
                        )
                    market_rules = await self.exchange.get_market_trade_rules(symbol, reference_price=current_price)
                    min_notional = float((market_rules or {}).get("min_cost") or 0.0)
                    sell_notional = float(sell_amount) * float(current_price)
                    if min_notional > 0 and sell_notional < min_notional:
                        # Binance won't accept this dust-sized close; clear local position so bot doesn't stay stuck.
                        state.add_log(
                            f"Dust close for {symbol}: order value {sell_notional:.6f} {settings.QUOTE_ASSET} "
                            f"is below Binance minimum {min_notional:.6f}. Marking trade closed locally."
                        )
                        trade_pnl = (current_price - trade_info["entry_price"]) * sell_amount
                        if symbol in state.active_trades:
                            state.active_trades[symbol].amount = sell_amount
                        state.close_trade(symbol, current_price, exit_commission=0.0)
                        if state.closed_trades:
                            closed_trade = state.closed_trades[-1]
                            closed_trade.stop_loss_price = float(trade_info.get("stop_loss_price", closed_trade.stop_loss_price))
                            closed_trade.hard_stop_price = float(trade_info.get("hard_stop_price", closed_trade.hard_stop_price))
                            closed_trade.high_water_price = float(trade_info.get("high_water_price", closed_trade.high_water_price or closed_trade.entry_price))
                            closed_trade.base_profit_target_pct = float(trade_info.get("base_profit_target_pct", closed_trade.base_profit_target_pct))
                            closed_trade.profit_target_pct = float(trade_info.get("profit_target_pct", closed_trade.profit_target_pct))
                            closed_trade.quick_profit_pct = float(trade_info.get("quick_profit_pct", closed_trade.quick_profit_pct))
                            closed_trade.profit_target_price = float(trade_info.get("profit_target_price", closed_trade.profit_target_price))
                            closed_trade.quick_profit_price = float(trade_info.get("quick_profit_price", closed_trade.quick_profit_price))
                            closed_trade.exit_reason = reason
                        if symbol in self.active_trades:
                            del self.active_trades[symbol]
                        self.risk_manager.current_trades = max(0, self.risk_manager.current_trades - 1)
                        self.risk_manager.record_trade_execution(symbol, time.time())
                        self.next_close_attempt.pop(symbol, None)
                        self.close_failures.pop(symbol, None)
                        self._record_trade_outcome(trade_pnl)
                        state.set_activity("Waiting for signals...")
                        return
                else:
                    retry_delay = min(60, 5 * (2 ** self.close_failures.get(symbol, 0)))
                    self.close_failures[symbol] = self.close_failures.get(symbol, 0) + 1
                    self.next_close_attempt[symbol] = time.time() + retry_delay
                    state.add_log(
                        f"Sell failed for {symbol}: no free {base_asset} available on Binance. Retrying in {retry_delay}s."
                    )
                    state.set_activity("Sell failed. Position still open.")
                    return

                order = await self.executor.place_sell_market(symbol, sell_amount, reference_price=current_price)
                if not order:
                    order_error = getattr(self.exchange, "last_order_error", None)
                    retry_delay = min(60, 5 * (2 ** self.close_failures.get(symbol, 0)))
                    self.close_failures[symbol] = self.close_failures.get(symbol, 0) + 1
                    self.next_close_attempt[symbol] = time.time() + retry_delay
                    if order_error:
                        state.add_log(f"Sell failed for {symbol}: {order_error}. Retrying in {retry_delay}s.")
                    else:
                        state.add_log(f"Sell failed for {symbol}. Retrying in {retry_delay}s.")
                    state.set_activity("Sell failed. Position still open.")
                    return

                exit_price = float(order.get("average") or current_price)
                trade_pnl = (exit_price - trade_info["entry_price"]) * sell_amount
                live_commission = await self.exchange.extract_commission_in_quote(
                    order,
                    symbol,
                    reference_price=exit_price,
                    quote_asset=settings.QUOTE_ASSET,
                )
                closed_net_pnl = trade_pnl

                trade_info["amount"] = sell_amount
                if symbol in state.active_trades:
                    state.active_trades[symbol].amount = sell_amount
                state.close_trade(symbol, exit_price, exit_commission=live_commission if state.test_balance is None else 0.0)
                if state.closed_trades:
                    closed_trade = state.closed_trades[-1]
                    closed_trade.stop_loss_price = float(trade_info.get("stop_loss_price", closed_trade.stop_loss_price))
                    closed_trade.hard_stop_price = float(trade_info.get("hard_stop_price", closed_trade.hard_stop_price))
                    closed_trade.high_water_price = float(trade_info.get("high_water_price", closed_trade.high_water_price or closed_trade.entry_price))
                    closed_trade.base_profit_target_pct = float(trade_info.get("base_profit_target_pct", closed_trade.base_profit_target_pct))
                    closed_trade.profit_target_pct = float(trade_info.get("profit_target_pct", closed_trade.profit_target_pct))
                    closed_trade.quick_profit_pct = float(trade_info.get("quick_profit_pct", closed_trade.quick_profit_pct))
                    closed_trade.profit_target_price = float(trade_info.get("profit_target_price", closed_trade.profit_target_price))
                    closed_trade.quick_profit_price = float(trade_info.get("quick_profit_price", closed_trade.quick_profit_price))
                    closed_trade.exit_reason = reason
                del self.active_trades[symbol]
                self.risk_manager.current_trades = max(0, self.risk_manager.current_trades - 1)
                self.risk_manager.record_trade_execution(symbol, time.time())

                if state.test_balance is None:
                    new_balance = await self.exchange.fetch_balance(settings.QUOTE_ASSET)
                    state.update_balance(new_balance)
                    if live_commission > 0:
                        state.total_commission_paid += live_commission
                        state.add_log(f"Live commission: ${live_commission:.4f}")
                        if state.closed_trades:
                            state.closed_trades[-1].exit_commission = live_commission
                            state.closed_trades[-1].commission_paid = (
                                float(state.closed_trades[-1].entry_commission or 0.0) + live_commission
                            )
                            state.closed_trades[-1].net_pnl = (
                                float(state.closed_trades[-1].pnl or 0.0)
                                - float(state.closed_trades[-1].commission_paid or 0.0)
                            )
                            closed_net_pnl = float(state.closed_trades[-1].net_pnl)
                        state.record_equity_point(note=f"{symbol} commission")
                    else:
                        state.save_state()
                else:
                    commission_rate = self._simulated_commission_rate(symbol, exit_price)
                    commission = exit_price * sell_amount * commission_rate
                    state.test_balance -= commission
                    state.total_commission_paid += commission
                    state.add_log(f"Simulated commission ({commission_rate * 100:.2f}%): ${commission:.4f}")
                    if state.closed_trades:
                        state.closed_trades[-1].exit_commission = commission
                        state.closed_trades[-1].commission_paid = (
                            float(state.closed_trades[-1].entry_commission or 0.0) + commission
                        )
                        state.closed_trades[-1].net_pnl = (
                            float(state.closed_trades[-1].pnl or 0.0) - float(state.closed_trades[-1].commission_paid or 0.0)
                        )
                        closed_net_pnl = float(state.closed_trades[-1].net_pnl)
                    state.record_equity_point(note=f"{symbol} commission")

                self.next_close_attempt.pop(symbol, None)
                self.close_failures.pop(symbol, None)
            except Exception as exc:
                logger.error("Immediate sell failed: %s", exc)
                retry_delay = min(60, 5 * (2 ** self.close_failures.get(symbol, 0)))
                self.close_failures[symbol] = self.close_failures.get(symbol, 0) + 1
                self.next_close_attempt[symbol] = time.time() + retry_delay
                state.add_log(f"Sell failed for {symbol}: {exc}. Retrying in {retry_delay}s.")
                state.set_activity("Sell failed. Position still open.")
                return

            self._record_trade_outcome(trade_pnl)
            state.set_activity("Waiting for signals...")
        finally:
            self.closing_symbols.discard(symbol)

    def _build_trade_plan(self, symbol, df, context):
        price = float(df.iloc[-1]["close"])
        atr = float(df.iloc[-1]["atr"] or 0.0)
        atr_pct = (atr / price) if price > 0 else 0.0
        mode_overrides = self._mode_trade_plan_overrides()
        base_stop_pct = atr_pct * 1.8
        if self._is_small_account():
            base_stop_pct *= 0.9
        stop_pct = base_stop_pct * mode_overrides["stop_mult"]
        stop_pct = max(float(settings.MIN_STOP_LOSS_PCT), stop_pct)
        stop_pct = min(stop_pct, float(settings.MAX_STOP_LOSS_PCT), float(settings.HARD_STOP_LOSS))
        if context.get("age_days", 9999) <= 3:
            profit_target_pct = settings.PROFIT_TARGET * mode_overrides["profit_mult"]
        else:
            profit_target_pct = max(
                settings.QUICK_PROFIT_TARGET * mode_overrides["quick_profit_mult"],
                settings.PROFIT_TARGET * 0.85 * mode_overrides["profit_mult"],
            )

        minimum_target = stop_pct * float(settings.MIN_REWARD_TO_RISK_RATIO)
        profit_target_pct = max(profit_target_pct, minimum_target)
        profit_target_pct = max(profit_target_pct, float(getattr(settings, "MIN_PROFIT_TARGET_PCT", 0.0)))
        quick_profit_pct = max(
            settings.QUICK_PROFIT_TARGET * mode_overrides["quick_profit_mult"],
            stop_pct * 0.9,
        )
        quick_profit_pct = max(quick_profit_pct, float(getattr(settings, "MIN_QUICK_PROFIT_TARGET_PCT", 0.0)))

        return {
            "stop_pct": stop_pct,
            "profit_target_pct": profit_target_pct,
            "quick_profit_pct": quick_profit_pct,
        }

    def _simulated_commission_rate(self, symbol, current_price):
        """
        Tiered test fee model:
        - normal market: 0.1% per execution
        - high movement: 0.5%
        - extreme movement: 1.0%
        """
        base_rate = float(getattr(settings, "SIMULATED_COMMISSION_BASE", settings.SIMULATED_COMMISSION))
        df = self.market_data.get(symbol)
        if df is None or df.empty:
            return base_rate

        lookback = max(2, int(getattr(settings, "SIMULATED_COMMISSION_MOVEMENT_LOOKBACK", 5)))
        window = df.tail(lookback)
        if window.empty:
            return base_rate

        reference_price = float(current_price or window.iloc[-1]["close"] or 0.0)
        if reference_price <= 0:
            return base_rate

        high = float(window["high"].max())
        low = float(window["low"].min())
        movement_pct = max(0.0, (high - low) / reference_price)

        high_threshold = float(getattr(settings, "SIMULATED_COMMISSION_HIGH_MOVE_PCT", 0.08))
        extreme_threshold = float(getattr(settings, "SIMULATED_COMMISSION_EXTREME_MOVE_PCT", 0.15))
        high_rate = float(getattr(settings, "SIMULATED_COMMISSION_HIGH", 0.005))
        extreme_rate = float(getattr(settings, "SIMULATED_COMMISSION_EXTREME", 0.01))

        if movement_pct >= extreme_threshold:
            return extreme_rate
        if movement_pct >= high_threshold:
            return high_rate
        return base_rate

    async def monitor_loop(self):
        while True:
            try:
                self._apply_time_slot_gate()
                await self.refresh_trading_universe()

                for symbol, flagged in list(state.manual_close_flags.items()):
                    if flagged and symbol in self.active_trades:
                        price = await self._latest_price_with_fallback(symbol)
                        if price is None:
                            now = time.time()
                            last_log_at = float(self.manual_close_wait_logged_at.get(symbol, 0.0) or 0.0)
                            if now - last_log_at >= 15:
                                state.add_log(f"Manual close pending for {symbol}: waiting for live price.")
                                self.manual_close_wait_logged_at[symbol] = now
                            continue
                        await self._force_close_trade(symbol, price, "Manual UI close")
                        state.manual_close_flags[symbol] = False
                        self.manual_close_wait_logged_at.pop(symbol, None)

                for symbol in list(self.active_trades.keys()):
                    price = await self._latest_price_with_fallback(symbol)
                    if price is not None:
                        trade_info = self.active_trades.get(symbol)
                        if trade_info and symbol in state.active_trades:
                            state.active_trades[symbol].pnl = (price - trade_info["entry_price"]) * trade_info["amount"]
                        await self.check_strategy_signals(symbol, current_price_override=price, allow_entry=False, candle_closed=False)
                    else:
                        self._clear_entry_confirmation(symbol)
            except Exception as exc:
                logger.error("Monitor loop error: %s", exc)
            await asyncio.sleep(1)

    async def on_candle_update(self, payload, stream_name=None):
        try:
            self.last_stream_message_at = time.time()
            kline = payload["k"]
            symbol_raw = payload.get("s") or (stream_name.split("@")[0].upper() if stream_name else "")
            symbol = next((s for s in self.trading_symbols if s.replace("/", "") == symbol_raw), symbol_raw)

            timestamp = kline["t"]
            current_price = float(kline["c"])
            candle_closed = bool(kline.get("x"))
            new_candle = {
                "timestamp": timestamp,
                "open": float(kline["o"]),
                "high": float(kline["h"]),
                "low": float(kline["l"]),
                "close": current_price,
                "volume": float(kline["v"]),
            }

            if symbol in self.active_trades and symbol in state.active_trades:
                trade_info = self.active_trades[symbol]
                state.active_trades[symbol].pnl = (current_price - trade_info["entry_price"]) * trade_info["amount"]
                await self.check_strategy_signals(symbol, current_price_override=current_price, allow_entry=False, candle_closed=False)

            df = self.market_data.get(symbol, pd.DataFrame())
            if df.empty:
                df = pd.DataFrame([new_candle])
            else:
                last_ts = df.iloc[-1]["timestamp"]
                if timestamp == last_ts:
                    for col, value in new_candle.items():
                        df.at[df.index[-1], col] = value
                elif timestamp > last_ts:
                    df = pd.concat([df, pd.DataFrame([new_candle])], ignore_index=True)

            df = df.tail(500)
            df = self.technicals.calculate_indicators(df, settings)
            self.market_data[symbol] = df
            if candle_closed:
                await self.check_strategy_signals(symbol, current_price_override=current_price, allow_entry=True, candle_closed=True)
            elif (
                symbol not in self.active_trades
                and not self._is_steady_mode()
                and self._should_check_intrabar_entry(df, current_price)
            ):
                await self.check_strategy_signals(symbol, current_price_override=current_price, allow_entry=True, candle_closed=False)
        except Exception as exc:
            logger.error("Error in on_candle_update: %s", exc)

    async def on_orderbook_update(self, payload, stream_name=None):
        try:
            self.last_stream_message_at = time.time()
            symbol_raw = payload.get("s") or (stream_name.split("@")[0].upper() if stream_name else "")
            symbol = next((s for s in self.trading_symbols if s.replace("/", "") == symbol_raw), symbol_raw)
            previous_signal = self.orderbook_data.get(symbol)
            self.orderbook_data[symbol] = self.technicals.calculate_orderbook_signal(payload, previous_signal)
        except Exception as exc:
            logger.error("Error in on_orderbook_update: %s", exc)

    async def _try_open_trade(self, symbol, df, current_price, reason, context):
        if symbol in self.active_trades or symbol in self.entry_symbols:
            return

        self.entry_symbols.add(symbol)
        try:
            can_trade, trade_gate_reason = self.risk_manager.check_new_trade_allowance(
                symbol,
                time.time(),
                cooldown_minutes=self._cooldown_minutes_for_current_mode(),
                active_trade_count=len(self.active_trades),
            )
            if not can_trade:
                self._log_entry_rejection(symbol, trade_gate_reason, throttle_seconds=60)
                return

            total_allocated = sum(t["entry_price"] * t["amount"] for t in self.active_trades.values())
            balance = state.test_balance if state.test_balance is not None else await self.exchange.fetch_balance(settings.QUOTE_ASSET)
            free_balance = max(0.0, balance - total_allocated)
            if state.test_balance is None:
                state.update_balance(balance)

            trade_plan = self._build_trade_plan(symbol, df, context)
            risk_factor = max(0.0, min(1.0, state.risk_percentage / 100.0))
            target_position_value = free_balance * min(risk_factor, settings.POSITION_SIZE_CAP)
            if free_balance <= 0:
                message = (
                    f"Skipped {symbol}: insufficient Binance free balance. "
                    f"Available {free_balance:.2f} {settings.QUOTE_ASSET}, risk target {target_position_value:.2f} {settings.QUOTE_ASSET}."
                )
                logger.info(message)
                state.add_log(message)
                return

            amount = self.risk_manager.calculate_position_size(
                free_balance,
                current_price,
                custom_risk=risk_factor,
                custom_sl=trade_plan["stop_pct"],
            )
            # Hard-cap per-trade allocation by slider risk percentage.
            if current_price > 0 and target_position_value > 0:
                allocation_cap_amount = target_position_value / current_price
                amount = min(amount, allocation_cap_amount)
            max_affordable_amount = (free_balance * 0.98) / current_price if current_price > 0 else 0.0
            if amount * current_price > free_balance * 0.98:
                amount = max_affordable_amount

            market_rules = await self.exchange.get_market_trade_rules(symbol, reference_price=current_price)
            min_cost = market_rules["min_cost"]
            current_cost = amount * current_price
            if min_cost and current_cost < min_cost and free_balance >= min_cost:
                amount = min_cost / current_price

            amount, amount_error = await self.exchange.normalize_order_amount(
                symbol,
                amount,
                reference_price=current_price,
            )
            if amount is None:
                logger.info("Skipping buy for %s, invalid order amount: %s", symbol, amount_error)
                state.add_log(f"Skipped {symbol}: {amount_error}")
                return

            if amount > max_affordable_amount > 0:
                amount = max_affordable_amount
                amount, amount_error = await self.exchange.normalize_order_amount(
                    symbol,
                    amount,
                    reference_price=current_price,
                )
                if amount is None:
                    logger.info("Skipping buy for %s, invalid affordable amount: %s", symbol, amount_error)
                    state.add_log(f"Skipped {symbol}: {amount_error}")
                    return

            order_cost = amount * current_price
            if min_cost and order_cost < min_cost:
                message = (
                    f"Skipped {symbol}: free balance {free_balance:.2f} {settings.QUOTE_ASSET} "
                    f"is below Binance minimum notional {min_cost:.2f} {settings.QUOTE_ASSET}."
                )
                logger.info(message)
                state.add_log(message)
                return

            if order_cost > free_balance * 0.98:
                message = (
                    f"Skipped {symbol}: insufficient Binance free balance for risk-based order. "
                    f"Needed {order_cost:.2f} {settings.QUOTE_ASSET}, available {free_balance:.2f} {settings.QUOTE_ASSET}, "
                    f"configured risk {state.risk_percentage:.0f}%."
                )
                logger.info(message)
                state.add_log(message)
                return

            if amount <= 0:
                state.add_log(
                    f"Skipped {symbol}: calculated order size is zero at {state.risk_percentage:.0f}% risk."
                )
                return

            logger.info("== SIGNAL BUY: %s at %s. Reason: %s ==", symbol, current_price, reason)
            state.set_activity(f"Buying {symbol} at {current_price}...")
            state.add_log(
                f"BUY {symbol} @ {current_price} ({reason}; 24h {context.get('price_change_pct', 0):.2f}%, mode {self._effective_bot_mode()})"
            )

            order = await self.executor.place_buy_market(symbol, amount, reference_price=current_price)
            if not order:
                if state.test_balance is None:
                    refreshed_balance = await self.exchange.fetch_balance(settings.QUOTE_ASSET)
                    state.update_balance(refreshed_balance)
                    state.add_log(
                        f"Buy failed for {symbol}: Binance rejected the order. "
                        f"Free balance now {refreshed_balance:.2f} {settings.QUOTE_ASSET}."
                    )
                state.set_activity("Waiting for signals...")
                return

            entry_price = float(order.get("average") or current_price)
            filled_amount = self.exchange.extract_net_filled_amount(order, symbol, fallback_amount=amount)
            live_commission = await self.exchange.extract_commission_in_quote(
                order,
                symbol,
                reference_price=entry_price,
                quote_asset=settings.QUOTE_ASSET,
            )

            entry_commission = 0.0
            if state.test_balance is not None:
                commission_rate = self._simulated_commission_rate(symbol, entry_price)
                commission = entry_price * filled_amount * commission_rate
                state.test_balance -= commission
                state.total_commission_paid += commission
                entry_commission = commission
                state.add_log(f"Simulated commission ({commission_rate * 100:.2f}%): ${commission:.4f}")
            else:
                new_balance = await self.exchange.fetch_balance(settings.QUOTE_ASSET)
                state.update_balance(new_balance)
                if live_commission > 0:
                    state.total_commission_paid += live_commission
                    entry_commission = live_commission
                    state.add_log(f"Live commission: ${live_commission:.4f}")

            stop_loss_price = entry_price * (1 - trade_plan["stop_pct"])
            executed_at = time.time()
            trade_payload = {
                "entry_price": entry_price,
                "stop_loss_price": stop_loss_price,
                "amount": filled_amount,
                "timestamp": executed_at,
                "high_water_price": entry_price,
                "hard_stop_price": entry_price * (1 - settings.HARD_STOP_LOSS),
                "base_profit_target_pct": trade_plan["profit_target_pct"],
                "profit_target_pct": trade_plan["profit_target_pct"],
                "quick_profit_pct": trade_plan["quick_profit_pct"],
                "profit_target_price": entry_price * (1 + trade_plan["profit_target_pct"]),
                "quick_profit_price": entry_price * (1 + trade_plan["quick_profit_pct"]),
            }
            self.active_trades[symbol] = trade_payload

            state.add_active_trade(
                Trade(
                    symbol=symbol,
                    entry_price=entry_price,
                    amount=filled_amount,
                    timestamp=trade_payload["timestamp"],
                    stop_loss_price=stop_loss_price,
                    hard_stop_price=trade_payload["hard_stop_price"],
                    base_profit_target_pct=trade_plan["profit_target_pct"],
                    profit_target_pct=trade_plan["profit_target_pct"],
                    quick_profit_pct=trade_plan["quick_profit_pct"],
                    profit_target_price=trade_payload["profit_target_price"],
                    quick_profit_price=trade_payload["quick_profit_price"],
                    high_water_price=entry_price,
                    entry_commission=entry_commission,
                    commission_paid=entry_commission,
                )
            )
            self.risk_manager.current_trades += 1
            self.risk_manager.record_trade_execution(symbol, executed_at)
            self.last_entry_time = executed_at
            self._clear_entry_confirmation(symbol)
            logger.info(
                "Trade entered: %s @ %s, SL: %s, TP: %s",
                symbol,
                entry_price,
                stop_loss_price,
                trade_payload["profit_target_price"],
            )
            state.set_activity("Waiting for signals...")
        finally:
            self.entry_symbols.discard(symbol)

    async def check_strategy_signals(self, symbol, current_price_override=None, allow_entry=True, candle_closed=False):
        df = self.market_data.get(symbol)
        if df is None or len(df) < 25:
            return

        current_price = float(current_price_override if current_price_override is not None else df.iloc[-1]["close"])
        adaptive_profile = self._adaptive_trade_profile(symbol=symbol)

        if symbol in self.active_trades:
            self._clear_entry_confirmation(symbol)
            trade_info = self.active_trades[symbol]
            mode_overrides = self._mode_trade_plan_overrides()
            higher_timeframes = self._get_higher_timeframe_context(symbol)
            current_rsi = float(df.iloc[-1]["rsi"])
            current_macd = float(df.iloc[-1]["macd"])
            current_signal = float(df.iloc[-1]["macd_signal"])
            ema_fast = float(df.iloc[-1]["ema_9"])
            ema_slow = float(df.iloc[-1]["ema_21"])
            profit_percent = (current_price - trade_info["entry_price"]) / trade_info["entry_price"]
            hold_seconds = time.time() - trade_info["timestamp"]
            trade_info["high_water_price"] = max(float(trade_info.get("high_water_price", trade_info["entry_price"])), current_price)
            peak_profit_percent = (trade_info["high_water_price"] - trade_info["entry_price"]) / trade_info["entry_price"]
            peak_retrace_percent = max(0.0, peak_profit_percent - profit_percent)
            trend_supports_patience = self._trend_supports_patience(
                symbol,
                df,
                current_rsi,
                current_macd,
                current_signal,
                ema_fast,
                ema_slow,
            )
            patience_mode = (
                trend_supports_patience
                and profit_percent >= -settings.NEGLIGIBLE_LOSS_PCT
                and hold_seconds <= settings.PATIENCE_EXTENSION_SECONDS
            )
            post_entry_patience = (
                hold_seconds <= settings.POST_ENTRY_MOMENTUM_PATIENCE_SECONDS
                and self._post_entry_structure_intact(
                    df,
                    trade_info,
                    current_price,
                    ema_fast,
                    ema_slow,
                    current_macd,
                    current_signal,
                )
            )
            recent_trade_window = df.tail(5)
            consolidation_range_pct = (
                (float(recent_trade_window["high"].max()) - float(recent_trade_window["low"].min())) / current_price
            ) if current_price > 0 and not recent_trade_window.empty else 0.0

            baseline_fee_rate = float(getattr(settings, "SIMULATED_COMMISSION_BASE", settings.SIMULATED_COMMISSION))
            if state.test_balance is None:
                expected_fee_rate = baseline_fee_rate
            else:
                expected_fee_rate = self._simulated_commission_rate(symbol, current_price)
            commission_cover_pct = max(
                float(settings.BREAKEVEN_FEE_BUFFER),
                (2.0 * expected_fee_rate) + 0.0005,
            )
            protected_stop_floor_pct = max(
                float(getattr(settings, "SECURE_PROFIT_FLOOR_PCT", settings.PROTECTED_STOP_MIN_ARM_PCT)),
                float(getattr(settings, "PROTECTED_STOP_MIN_ARM_PCT", 0.0032)),
            )
            secure_profit_trigger_pct = max(
                float(getattr(settings, "SECURE_PROFIT_TRIGGER_PCT", 0.006)),
                protected_stop_floor_pct + 0.002,
            )

            previous_stop = float(trade_info["stop_loss_price"])
            should_arm_breakeven = (
                peak_profit_percent >= secure_profit_trigger_pct
                and hold_seconds >= min(
                    settings.BREAKEVEN_MIN_HOLD_SECONDS,
                    max(30, int(settings.BREAKEVEN_MIN_HOLD_SECONDS * 0.5)),
                )
                and profit_percent > 0
            )
            if should_arm_breakeven:
                breakeven_stop = trade_info["entry_price"] * (1 + protected_stop_floor_pct)
                trade_info["stop_loss_price"] = max(trade_info["stop_loss_price"], breakeven_stop)
                if (
                    trade_info["stop_loss_price"] > previous_stop
                    and not trade_info.get("breakeven_armed")
                ):
                    trade_info["breakeven_armed"] = True
                    state.add_log(
                        f"{symbol} protected stop armed at ${trade_info['stop_loss_price']:.4f} "
                        f"(secured floor {protected_stop_floor_pct * 100:.2f}%)."
                    )

            if (
                peak_profit_percent >= mode_overrides["profit_protection_trigger"]
                and profit_percent >= settings.PROTECTED_STOP_MIN_PROFIT
            ):
                protected_profit_stop = trade_info["entry_price"] * (1 + mode_overrides["profit_protection_floor"])
                trade_info["stop_loss_price"] = max(trade_info["stop_loss_price"], protected_profit_stop)

            # Stage-based profit locking: keep trades running while ratcheting stop into profit.
            quick_target_pct = float(trade_info.get("quick_profit_pct", settings.QUICK_PROFIT_TARGET))
            base_target_pct = float(trade_info.get("base_profit_target_pct", trade_info.get("profit_target_pct", settings.PROFIT_TARGET)))
            full_target_pct = base_target_pct
            if peak_profit_percent >= secure_profit_trigger_pct:
                quick_lock_pct = max(protected_stop_floor_pct, quick_target_pct * 0.32)
                trade_info["stop_loss_price"] = max(
                    trade_info["stop_loss_price"],
                    trade_info["entry_price"] * (1 + quick_lock_pct),
                )
            if peak_profit_percent >= full_target_pct:
                full_lock_pct = max(mode_overrides["profit_protection_floor"], full_target_pct * 0.45)
                trade_info["stop_loss_price"] = max(
                    trade_info["stop_loss_price"],
                    trade_info["entry_price"] * (1 + full_lock_pct),
                )
            if peak_profit_percent >= (full_target_pct * 1.35):
                extended_lock_pct = max(mode_overrides["profit_protection_floor"], full_target_pct * 0.65)
                trade_info["stop_loss_price"] = max(
                    trade_info["stop_loss_price"],
                    trade_info["entry_price"] * (1 + extended_lock_pct),
                )

            if profit_percent >= settings.TRAILING_START_PROFIT:
                new_stop = self.risk_manager.update_trailing_stop(
                    current_price,
                    trade_info["stop_loss_price"],
                    custom_trail=settings.TRAILING_STOP,
                )
                trade_info["stop_loss_price"] = max(trade_info["stop_loss_price"], new_stop)
            if symbol in state.active_trades:
                state.active_trades[symbol].stop_loss_price = trade_info["stop_loss_price"]
                state.active_trades[symbol].high_water_price = trade_info["high_water_price"]

            bearish_reversal = (
                current_macd < current_signal
                and ema_fast < ema_slow
                and current_rsi < 52
            )
            min_hold_required = max(mode_overrides["min_hold_seconds"], mode_overrides["min_hold_after_entry_seconds"])
            last_open = float(df.iloc[-1]["open"])
            last_close = float(df.iloc[-1]["close"])
            last_high = float(df.iloc[-1]["high"])
            last_low = float(df.iloc[-1]["low"])
            candle_range = max(last_high - last_low, 1e-12)
            candle_body = abs(last_close - last_open)
            candle_body_pct = candle_body / max(last_open, 1e-12)
            small_red_candle = (
                last_close < last_open
                and candle_body_pct <= settings.SMALL_RED_CANDLE_BODY_PCT
                and (candle_body / candle_range) <= 0.45
            )
            confirm_window = df.tail(max(2, settings.EXIT_CONFIRM_BEARISH_CANDLES + 1))
            bearish_confirms = int((confirm_window["close"] < confirm_window["open"]).sum())
            bearish_confirmed = bearish_confirms >= settings.EXIT_CONFIRM_BEARISH_CANDLES
            runner_state = self._runner_hold_state(
                symbol,
                df,
                current_price,
                trade_info,
                current_rsi,
                current_macd,
                current_signal,
                ema_fast,
                ema_slow,
                peak_profit_percent,
                peak_retrace_percent,
                bearish_confirmed,
            )
            runner_active = bool(runner_state["runner_active"])
            momentum_fading = bool(runner_state["momentum_fading"])

            if runner_active:
                extended_target_pct = min(
                    base_target_pct * settings.RUNNER_EXTENDED_TARGET_MULTIPLIER,
                    max(
                        float(trade_info.get("profit_target_pct", base_target_pct)),
                        max(base_target_pct * 1.15, profit_percent + max(0.0025, base_target_pct * 0.3)),
                    ),
                )
                if extended_target_pct > float(trade_info.get("profit_target_pct", base_target_pct)):
                    trade_info["profit_target_pct"] = extended_target_pct
                    trade_info["profit_target_price"] = trade_info["entry_price"] * (1 + extended_target_pct)
            else:
                trade_info["profit_target_pct"] = max(float(trade_info.get("profit_target_pct", base_target_pct)), base_target_pct)
                trade_info["profit_target_price"] = max(
                    float(trade_info.get("profit_target_price", 0.0) or 0.0),
                    trade_info["entry_price"] * (1 + float(trade_info["profit_target_pct"])),
                )

            should_sell = False
            reason = ""
            protected_stop_active = trade_info["stop_loss_price"] >= (
                trade_info["entry_price"] * (1 + protected_stop_floor_pct)
            )
            soft_exit_ready = candle_closed or not settings.SOFT_EXIT_ON_CANDLE_CLOSE_ONLY
            bearish_exit_ready = (
                soft_exit_ready
                and hold_seconds >= settings.MIN_HOLD_FOR_BEARISH_EXIT_SECONDS
                and peak_retrace_percent >= adaptive_profile.get("min_peak_retrace_for_bearish_exit", settings.MIN_PEAK_RETRACE_FOR_BEARISH_EXIT)
            )
            sideways_profit_exit_ready = (
                soft_exit_ready
                and hold_seconds >= settings.SIDEWAYS_TAKE_PROFIT_MIN_SECONDS
                and profit_percent >= settings.SIDEWAYS_TAKE_PROFIT_MIN_PCT
                and consolidation_range_pct <= settings.SIDEWAYS_TAKE_PROFIT_RANGE_PCT
                and momentum_fading
            )
            failed_momentum_early_exit_ready = (
                soft_exit_ready
                and hold_seconds >= max(90, int(settings.MIN_HOLD_FOR_BEARISH_EXIT_SECONDS * 0.45))
                and bearish_reversal
                and bearish_confirmed
                and profit_percent <= -settings.NEGLIGIBLE_LOSS_PCT
                and not runner_active
                and not post_entry_patience
            )
            quick_reversal_sl_exit_ready = (
                soft_exit_ready
                and hold_seconds >= float(getattr(settings, "QUICK_REVERSAL_EXIT_MIN_SECONDS", 75))
                and bearish_reversal
                and bearish_confirmed
                and peak_profit_percent <= float(getattr(settings, "QUICK_REVERSAL_EXIT_MAX_PEAK_PCT", 0.0035))
                and profit_percent <= float(getattr(settings, "QUICK_REVERSAL_EXIT_MAX_PROFIT_PCT", 0.0025))
                and current_price < ema_fast
                and current_price < float(df.iloc[-1]["vwap"]) * 0.999
                and not runner_active
                and not post_entry_patience
            )

            if current_price <= trade_info.get("hard_stop_price", trade_info["entry_price"] * (1 - settings.HARD_STOP_LOSS)):
                should_sell, reason = True, "Hard protection stop triggered"
            elif current_price <= trade_info["stop_loss_price"]:
                should_sell, reason = True, "Protected profit stop hit" if protected_stop_active else "Stop loss hit"
            elif quick_reversal_sl_exit_ready:
                should_sell, reason = True, "Quick reversal stop exit"
            elif (
                soft_exit_ready
                and profit_percent >= trade_info.get("quick_profit_pct", settings.QUICK_PROFIT_TARGET)
                and bearish_reversal
                and bearish_confirmed
                and not runner_active
            ):
                should_sell, reason = True, "Quick profit locked on reversal"
            elif (
                soft_exit_ready
                and hold_seconds >= settings.STOP_LOSS_GRACE_SECONDS
                and bearish_reversal
                and bearish_confirmed
                and not small_red_candle
                and not runner_active
                and not post_entry_patience
            ):
                should_sell, reason = True, "Momentum reversal exit"
            elif failed_momentum_early_exit_ready:
                should_sell, reason = True, "Momentum failed early (loss protection)"
            elif sideways_profit_exit_ready and not runner_active:
                should_sell, reason = True, "Sideways profit exit"
            elif state.manual_close_flags.get(symbol, False):
                should_sell, reason = True, "Manual UI close"

            if symbol in state.active_trades:
                state.active_trades[symbol].pnl = (current_price - trade_info["entry_price"]) * trade_info["amount"]
                state.active_trades[symbol].profit_target_pct = float(trade_info.get("profit_target_pct", base_target_pct))
                state.active_trades[symbol].profit_target_price = float(
                    trade_info.get("profit_target_price", trade_info["entry_price"] * (1 + float(trade_info.get("profit_target_pct", base_target_pct))))
                )

            if should_sell:
                state.manual_close_flags[symbol] = False
                await self._force_close_trade(symbol, current_price, reason)
            return

        if self._circuit_breaker_active():
            self._clear_entry_confirmation(symbol)
            if state.manual_trade_trigger:
                state.manual_trade_trigger = False
            return

        if not allow_entry:
            return

        if symbol in self.entry_symbols:
            return

        can_trade, trade_gate_reason = self.risk_manager.check_new_trade_allowance(
            symbol,
            time.time(),
            cooldown_minutes=self._cooldown_minutes_for_current_mode(),
            active_trade_count=len(self.active_trades),
        )
        if (not can_trade or not state.bot_enabled) and not state.manual_trade_trigger:
            if not state.bot_enabled or not can_trade:
                self._clear_entry_confirmation(symbol)
                self._log_entry_rejection(
                    symbol,
                    "Bot trading is disabled." if not state.bot_enabled else trade_gate_reason,
                    throttle_seconds=60,
                )
            return

        context = self.market_context.get(symbol, {"symbol": symbol, "safety_passed": False})
        orderbook_signal = self.orderbook_data.get(symbol, {"imbalance": 0.5, "support_rising": False})
        higher_timeframes = self._get_higher_timeframe_context(symbol)
        strategy_context = context
        if state.manual_trade_trigger:
            strategy_context = dict(context)
            strategy_context["manual_entry_override"] = True
        should_buy, reason = self.strategy.evaluate_buy(
            df,
            orderbook_signal,
            market_context=strategy_context,
            mode=self._effective_bot_mode(),
            higher_timeframes=higher_timeframes,
            adaptive_profile=adaptive_profile,
        )

        manual_override = False
        if state.manual_trade_trigger and symbol in self.trading_symbols:
            state.manual_trade_trigger = False
            if can_trade:
                if should_buy:
                    reason = f"Manual test trade confirmed: {reason}"
                    manual_override = True
                else:
                    state.add_log(
                        f"Manual trade skipped for {symbol}: {reason or 'no confirmed bullish momentum setup.'}"
                    )
                    return
            else:
                state.add_log(f"Manual trade skipped for {symbol}: {trade_gate_reason}")
                return

        if not should_buy:
            self._clear_entry_confirmation(symbol)
            self._log_entry_rejection(symbol, reason)
            return

        if not manual_override:
            confirmations = self._confirm_entry_signal(symbol, reason)
            required_confirmations = self._entry_confirmation_requirement(adaptive_profile=adaptive_profile)
            if self._should_fast_track_entry(
                reason,
                candle_closed=candle_closed,
                adaptive_profile=adaptive_profile,
            ):
                required_confirmations = max(1, required_confirmations - 1)
            if confirmations < required_confirmations:
                self._log_entry_rejection(
                    symbol,
                    f"Waiting for strategy confirmation ({confirmations}/{required_confirmations}) after {reason}.",
                    throttle_seconds=45,
                )
                return
            self._clear_entry_confirmation(symbol)

        await self._try_open_trade(symbol, df, current_price, reason, context)

    async def run(self):
        set_current_state(self.state)
        try:
            await self.initialize()
            self.startup_error = None
            self.ready_event.set()
            self.stream = MarketStream(
                self.trading_symbols,
                self.on_candle_update,
                self.on_orderbook_update,
            )

            state.bot_running = True
            logger.info("Starting live trading streams...")
            await asyncio.gather(
                self.stream.connect(),
                self.monitor_loop(),
            )
        except KeyboardInterrupt:
            logger.info("Shutting down gracefully...")
        except Exception as exc:
            self.startup_error = str(exc)
            self.ready_event.set()
            state.bot_running = False
            state.bot_enabled = False
            state.set_activity("Waiting for Binance connection. Open the app logs for details.")
            state.add_log(f"Startup paused: {exc}")
            state.save_state()
            logger.exception("Bot startup failed")
            while True:
                await asyncio.sleep(60)
        finally:
            if self.stream:
                await self.stream.disconnect()
            await self.market_discovery.close()
            await self.exchange.close()


if __name__ == "__main__":
    manager = MultiUserBotManager(ScalperBot)
    register_bot_manager(manager)
    api_host = os.getenv("HOST", "0.0.0.0")
    api_port = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))

    async def main():
        config = uvicorn.Config(app, host=api_host, port=api_port, log_level="error")
        server = uvicorn.Server(config)
        logger.info("Starting API server on %s:%s", api_host, api_port)
        await server.serve()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
