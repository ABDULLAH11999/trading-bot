from dataclasses import dataclass
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from user_profiles import normalize_email, user_data_dir
from security.hardening import redact_sensitive_text

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "data" / "state.json"
REPORT_RANGE_SECONDS = {
    "last_hour": 3600,
    "last_day": 86400,
    "last_week": 604800,
    "overall": None,
}


@dataclass
class Trade:
    symbol: str
    entry_price: float
    amount: float
    timestamp: float
    stop_loss_price: float
    hard_stop_price: float = 0.0
    base_profit_target_pct: float = 0.0
    profit_target_pct: float = 0.0
    quick_profit_pct: float = 0.0
    profit_target_price: float = 0.0
    quick_profit_price: float = 0.0
    high_water_price: Optional[float] = None
    side: str = "buy"
    status: str = "open"
    exit_price: Optional[float] = None
    exit_timestamp: Optional[float] = None
    pnl: float = 0.0
    entry_commission: float = 0.0
    exit_commission: float = 0.0
    commission_paid: float = 0.0
    net_pnl: float = 0.0
    exit_reason: str = ""


class BotState:
    def __init__(self, user_email: str = "", state_file: Optional[Path] = None):
        self.user_email = normalize_email(user_email)
        self.state_file = Path(state_file) if state_file else self._resolve_state_file()
        self.balance: float = 0.0
        self.quote_asset: str = "USDT"
        self.active_trades: Dict[str, Trade] = {}
        self.closed_trades: List[Trade] = []
        self.current_activity: str = "Initializing..."
        self.last_update: float = time.time()
        self.total_pnl: float = 0.0
        self.bot_running: bool = False
        self.bot_enabled: bool = False
        self.logs: List[str] = []
        self.symbols_data: Dict[str, Dict] = {}
        self.total_commission_paid: float = 0.0
        self.is_paper_trading: bool = True
        self.account_mode: str = "test"
        self.loaded_account_mode: bool = False
        self.account_states = {
            "test": self._empty_account_state("test"),
            "real": self._empty_account_state("real"),
        }

        self.bot_mode: str = "Flipping Scalper"
        self.risk_percentage: float = 85.0
        self.test_balance: Optional[float] = 100.0
        self.favorite_pairs_enabled: bool = False
        self.favorite_pairs: List[str] = []
        self.time_slots_enabled: bool = False
        self.time_slots: List[Dict[str, str]] = []
        self.manual_trade_trigger: bool = False
        self.manual_close_flags: Dict[str, bool] = {}
        self.start_time: float = time.time()

        self.load_state()
        self.bot_enabled = False

    def _resolve_state_file(self):
        if not self.user_email:
            return STATE_FILE
        return user_data_dir(self.user_email) / "state.json"

    def _empty_account_state(self, mode: str):
        now = time.time()
        return {
            "balance": 0.0,
            "quote_asset": "USDT",
            "test_balance": None if mode == "real" else 100.0,
            "total_pnl": 0.0,
            "total_commission_paid": 0.0,
            "active_trades": {},
            "closed_trades": [],
            "session_started_at": now,
            "last_reset_at": now,
            "equity_history": [],
        }

    def _serialize_trade(self, trade: Trade):
        return {
            "symbol": trade.symbol,
            "entry_price": trade.entry_price,
            "amount": trade.amount,
            "timestamp": trade.timestamp,
            "stop_loss_price": trade.stop_loss_price,
            "hard_stop_price": trade.hard_stop_price,
            "base_profit_target_pct": trade.base_profit_target_pct,
            "profit_target_pct": trade.profit_target_pct,
            "quick_profit_pct": trade.quick_profit_pct,
            "profit_target_price": trade.profit_target_price,
            "quick_profit_price": trade.quick_profit_price,
            "high_water_price": trade.high_water_price,
            "side": trade.side,
            "status": trade.status,
            "exit_price": trade.exit_price,
            "exit_timestamp": trade.exit_timestamp,
            "pnl": trade.pnl,
            "entry_commission": trade.entry_commission,
            "exit_commission": trade.exit_commission,
            "commission_paid": trade.commission_paid,
            "net_pnl": trade.net_pnl,
            "exit_reason": trade.exit_reason,
        }

    def _deserialize_trade(self, payload, default_status="closed"):
        entry_price = float(payload["entry_price"])
        base_profit_target_pct = float(payload.get("base_profit_target_pct", 0.0) or 0.0)
        profit_target_pct = float(payload.get("profit_target_pct", 0.0) or 0.0)
        quick_profit_pct = float(payload.get("quick_profit_pct", 0.0) or 0.0)
        profit_target_price = float(payload.get("profit_target_price", 0.0) or 0.0)
        quick_profit_price = float(payload.get("quick_profit_price", 0.0) or 0.0)
        if base_profit_target_pct <= 0 and profit_target_pct > 0:
            base_profit_target_pct = profit_target_pct
        if profit_target_price <= 0 and profit_target_pct > 0:
            profit_target_price = entry_price * (1 + profit_target_pct)
        if quick_profit_price <= 0 and quick_profit_pct > 0:
            quick_profit_price = entry_price * (1 + quick_profit_pct)
        return Trade(
            symbol=payload["symbol"],
            entry_price=entry_price,
            amount=float(payload["amount"]),
            timestamp=float(payload["timestamp"]),
            stop_loss_price=float(payload.get("stop_loss_price", 0.0)),
            hard_stop_price=float(payload.get("hard_stop_price", 0.0) or 0.0),
            base_profit_target_pct=base_profit_target_pct,
            profit_target_pct=profit_target_pct,
            quick_profit_pct=quick_profit_pct,
            profit_target_price=profit_target_price,
            quick_profit_price=quick_profit_price,
            high_water_price=float(payload.get("high_water_price", payload["entry_price"])),
            side=payload.get("side", "buy"),
            status=payload.get("status", default_status),
            exit_price=payload.get("exit_price"),
            exit_timestamp=payload.get("exit_timestamp"),
            pnl=float(payload.get("pnl", 0.0)),
            entry_commission=float(payload.get("entry_commission", 0.0) or 0.0),
            exit_commission=float(payload.get("exit_commission", 0.0) or 0.0),
            commission_paid=float(payload.get("commission_paid", 0.0) or 0.0),
            net_pnl=float(payload.get("net_pnl", 0.0) or 0.0),
            exit_reason=str(payload.get("exit_reason", "") or ""),
        )

    def _load_account_payload(self, payload, mode: str):
        account = self._empty_account_state(mode)
        if not isinstance(payload, dict):
            return account

        account["balance"] = float(payload.get("balance", 0.0) or 0.0)
        account["quote_asset"] = payload.get("quote_asset", "USDT")
        test_balance = payload.get("test_balance", None)
        account["test_balance"] = None if mode == "real" else test_balance
        account["total_pnl"] = float(payload.get("total_pnl", 0.0) or 0.0)
        account["total_commission_paid"] = float(payload.get("total_commission_paid", 0.0) or 0.0)
        account["session_started_at"] = float(payload.get("session_started_at", time.time()) or time.time())
        account["last_reset_at"] = float(payload.get("last_reset_at", account["session_started_at"]) or account["session_started_at"])

        active_trades = {}
        for symbol, trade_payload in (payload.get("active_trades", {}) or {}).items():
            try:
                active_trades[symbol] = self._deserialize_trade(trade_payload, default_status="open")
            except Exception:
                continue
        account["active_trades"] = active_trades

        closed_trades = []
        for trade_payload in (payload.get("closed_trades", []) or []):
            try:
                closed_trades.append(self._deserialize_trade(trade_payload, default_status="closed"))
            except Exception:
                continue
        account["closed_trades"] = closed_trades

        equity_history = []
        for point in (payload.get("equity_history", []) or []):
            try:
                equity_history.append({
                    "timestamp": float(point["timestamp"]),
                    "equity": float(point["equity"]),
                    "free_balance": float(point.get("free_balance", point["equity"])),
                    "allocated": float(point.get("allocated", 0.0)),
                    "unrealized_pnl": float(point.get("unrealized_pnl", 0.0)),
                    "realized_pnl": float(point.get("realized_pnl", 0.0)),
                    "note": str(point.get("note", "")),
                })
            except Exception:
                continue
        account["equity_history"] = equity_history[-1000:]
        return account

    def _sync_current_account_state(self):
        if self.account_mode not in self.account_states:
            self.account_states[self.account_mode] = self._empty_account_state(self.account_mode)
        account = self.account_states[self.account_mode]
        account["balance"] = float(self.balance or 0.0)
        account["quote_asset"] = self.quote_asset
        account["test_balance"] = None if self.account_mode == "real" else self.test_balance
        account["total_pnl"] = float(self.total_pnl or 0.0)
        account["total_commission_paid"] = float(self.total_commission_paid or 0.0)
        account["active_trades"] = {symbol: trade for symbol, trade in self.active_trades.items()}
        account["closed_trades"] = list(self.closed_trades[-500:])
        account["session_started_at"] = float(account.get("session_started_at") or self.start_time or time.time())
        account["last_reset_at"] = float(account.get("last_reset_at") or account["session_started_at"])
        account["equity_history"] = list(account.get("equity_history", []))[-1000:]

    def _apply_account_state(self, mode: str):
        account = self.account_states.get(mode) or self._empty_account_state(mode)
        self.balance = float(account.get("balance", 0.0) or 0.0)
        self.quote_asset = account.get("quote_asset", "USDT")
        self.test_balance = None if mode == "real" else account.get("test_balance", None)
        self.total_pnl = float(account.get("total_pnl", 0.0) or 0.0)
        self.total_commission_paid = float(account.get("total_commission_paid", 0.0) or 0.0)
        self.active_trades = dict(account.get("active_trades", {}))
        self.closed_trades = list(account.get("closed_trades", []))
        self.account_mode = mode
        self.is_paper_trading = mode != "real"

    def _current_total_allocated(self):
        return sum(trade.entry_price * trade.amount for trade in self.active_trades.values())

    def _current_total_unrealized(self):
        return sum(trade.pnl for trade in self.active_trades.values())

    def _current_equity(self):
        total_allocated = self._current_total_allocated()
        total_unrealized = self._current_total_unrealized()
        if self.test_balance is not None:
            return float(self.test_balance + total_unrealized)
        return float(self.balance + total_allocated + total_unrealized)

    def _equity_point(self, note="", timestamp=None):
        point_time = float(timestamp or time.time())
        total_allocated = self._current_total_allocated()
        total_unrealized = self._current_total_unrealized()
        if self.test_balance is not None:
            free_balance = float((self.test_balance or 0.0) - total_allocated)
        else:
            free_balance = float(self.balance or 0.0)
        return {
            "timestamp": point_time,
            "equity": round(self._current_equity(), 8),
            "free_balance": round(free_balance, 8),
            "allocated": round(total_allocated, 8),
            "unrealized_pnl": round(total_unrealized, 8),
            "realized_pnl": round(float(self.total_pnl or 0.0), 8),
            "note": note or "",
        }

    def record_equity_point(self, note="", timestamp=None, persist=True, force=False):
        self._sync_current_account_state()
        account = self.account_states[self.account_mode]
        point = self._equity_point(note=note, timestamp=timestamp)
        history = account.setdefault("equity_history", [])
        last_point = history[-1] if history else None
        if last_point and not force:
            if (
                abs(last_point.get("equity", 0.0) - point["equity"]) < 1e-9
                and abs(last_point.get("free_balance", 0.0) - point["free_balance"]) < 1e-9
                and abs(last_point.get("allocated", 0.0) - point["allocated"]) < 1e-9
            ):
                return
        history.append(point)
        account["equity_history"] = history[-1000:]
        if persist:
            self.save_state()

    def _estimate_starting_equity(self):
        unrealized = self._current_total_unrealized()
        return float(self._current_equity() - self.total_pnl - unrealized + self.total_commission_paid)

    def _rebuild_equity_history_if_missing(self):
        self._sync_current_account_state()
        account = self.account_states[self.account_mode]
        if account.get("equity_history"):
            return

        history = []
        current_equity = self._current_equity()
        starting_equity = self._estimate_starting_equity()
        base_time = float(account.get("last_reset_at") or account.get("session_started_at") or time.time())
        history.append({
            "timestamp": base_time,
            "equity": round(starting_equity, 8),
            "free_balance": round(starting_equity, 8),
            "allocated": 0.0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "note": "Session started",
        })

        running_equity = starting_equity
        closed_trades = sorted(
            self.closed_trades,
            key=lambda trade: float(trade.exit_timestamp or trade.timestamp or base_time),
        )
        for trade in closed_trades:
            trade_net = float(trade.net_pnl if trade.net_pnl else trade.pnl - trade.commission_paid)
            running_equity += trade_net
            history.append({
                "timestamp": float(trade.exit_timestamp or trade.timestamp or base_time),
                "equity": round(running_equity, 8),
                "free_balance": round(running_equity, 8),
                "allocated": 0.0,
                "unrealized_pnl": 0.0,
                "realized_pnl": round(running_equity - starting_equity, 8),
                "note": f"{trade.symbol} closed",
            })

        if not history or abs(history[-1]["equity"] - current_equity) > 1e-9:
            history.append({
                "timestamp": time.time(),
                "equity": round(current_equity, 8),
                "free_balance": round(current_equity if self.test_balance is not None else self.balance, 8),
                "allocated": round(self._current_total_allocated(), 8),
                "unrealized_pnl": round(self._current_total_unrealized(), 8),
                "realized_pnl": round(float(self.total_pnl or 0.0), 8),
                "note": "Current equity",
            })

        account["equity_history"] = history[-1000:]

    def load_state(self):
        if self.state_file.exists():
            try:
                with self.state_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                self.quote_asset = data.get("quote_asset", "USDT")
                self.test_balance = data.get("test_balance", 100.0)
                self.bot_mode = data.get("bot_mode", "Flipping Scalper")
                self.risk_percentage = max(0.0, min(100.0, data.get("risk_percentage", 85.0)))
                self.bot_enabled = data.get("bot_enabled", False)
                self.favorite_pairs_enabled = bool(data.get("favorite_pairs_enabled", False))
                self.favorite_pairs = [
                    str(symbol or "").strip().upper()
                    for symbol in (data.get("favorite_pairs") or [])
                    if str(symbol or "").strip()
                ]
                self.time_slots_enabled = bool(data.get("time_slots_enabled", False))
                self.time_slots = [
                    {
                        "start": str(slot.get("start") or "").strip(),
                        "end": str(slot.get("end") or "").strip(),
                    }
                    for slot in (data.get("time_slots") or [])
                    if isinstance(slot, dict) and str(slot.get("start") or "").strip() and str(slot.get("end") or "").strip()
                ]
                self.loaded_account_mode = "account_mode" in data
                self.account_mode = data.get("account_mode", "test")

                if "account_states" in data:
                    for mode in ("test", "real"):
                        self.account_states[mode] = self._load_account_payload((data.get("account_states") or {}).get(mode, {}), mode)
                else:
                    legacy_mode = self.account_mode if self.account_mode in {"test", "real"} else "test"
                    self.account_states[legacy_mode] = self._load_account_payload(data, legacy_mode)
                    other_mode = "real" if legacy_mode == "test" else "test"
                    self.account_states[other_mode] = self._empty_account_state(other_mode)
            except Exception:
                pass

        if self.account_mode not in {"test", "real"}:
            self.account_mode = "test"
        self._apply_account_state(self.account_mode)
        self.start_time = float(
            self.account_states[self.account_mode].get("session_started_at")
            or self.account_states[self.account_mode].get("last_reset_at")
            or time.time()
        )
        self._rebuild_equity_history_if_missing()
        if self.account_mode == "real":
            self.test_balance = None

    def save_state(self):
        try:
            self._sync_current_account_state()
            payload = {
                "quote_asset": self.quote_asset,
                "bot_mode": self.bot_mode,
                "risk_percentage": self.risk_percentage,
                "bot_enabled": self.bot_enabled,
                "favorite_pairs_enabled": self.favorite_pairs_enabled,
                "favorite_pairs": list(self.favorite_pairs),
                "time_slots_enabled": self.time_slots_enabled,
                "time_slots": list(self.time_slots),
                "account_mode": self.account_mode,
                "test_balance": self.test_balance,
                "account_states": {},
            }
            for mode, account in self.account_states.items():
                payload["account_states"][mode] = {
                    "balance": account.get("balance", 0.0),
                    "quote_asset": account.get("quote_asset", "USDT"),
                    "test_balance": None if mode == "real" else account.get("test_balance", None),
                    "total_pnl": account.get("total_pnl", 0.0),
                    "total_commission_paid": account.get("total_commission_paid", 0.0),
                    "active_trades": {
                        symbol: self._serialize_trade(trade)
                        for symbol, trade in (account.get("active_trades", {}) or {}).items()
                    },
                    "closed_trades": [
                        self._serialize_trade(trade)
                        for trade in (account.get("closed_trades", []) or [])[-500:]
                    ],
                    "session_started_at": account.get("session_started_at", time.time()),
                    "last_reset_at": account.get("last_reset_at", time.time()),
                    "equity_history": list((account.get("equity_history", []) or [])[-1000:]),
                }

            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with self.state_file.open("w", encoding="utf-8") as f:
                json.dump(payload, f)
        except Exception:
            pass

    def switch_account_mode(self, mode: str):
        selected_mode = (mode or "test").strip().lower()
        if selected_mode not in {"test", "real"}:
            selected_mode = "test"
        self._sync_current_account_state()
        if selected_mode not in self.account_states:
            self.account_states[selected_mode] = self._empty_account_state(selected_mode)
        self._apply_account_state(selected_mode)
        self.start_time = float(
            self.account_states[selected_mode].get("session_started_at")
            or self.account_states[selected_mode].get("last_reset_at")
            or time.time()
        )
        self._rebuild_equity_history_if_missing()
        self.save_state()

    def reset_state(self, initial_balance: Optional[float] = None):
        self.closed_trades = []
        self.active_trades = {}
        self.total_pnl = 0.0
        self.total_commission_paid = 0.0
        self.logs = []
        self.manual_trade_trigger = False
        self.manual_close_flags = {}
        if initial_balance is not None:
            if self.test_balance is not None:
                self.test_balance = initial_balance
            else:
                self.balance = initial_balance
        account = self.account_states.get(self.account_mode) or self._empty_account_state(self.account_mode)
        reset_at = time.time()
        account["session_started_at"] = reset_at
        account["last_reset_at"] = reset_at
        account["equity_history"] = []
        self.account_states[self.account_mode] = account
        self.start_time = reset_at
        self.current_activity = "Bot reset. Waiting for spot momentum signals..."
        self.last_update = reset_at
        self.record_equity_point(note="Bot reset", timestamp=reset_at, persist=False, force=True)
        self.save_state()

    def update_balance(self, balance: float):
        self.balance = balance
        self.last_update = time.time()
        self.record_equity_point(note="Balance sync", persist=False)
        self.save_state()

    def set_test_balance_baseline(self, balance: float):
        self.test_balance = float(balance)
        self.last_update = time.time()

        # In real mode this value is ignored, but we still persist safely.
        if self.account_mode != "test":
            self.save_state()
            return

        now = time.time()
        account = self.account_states.get(self.account_mode) or self._empty_account_state(self.account_mode)
        account["test_balance"] = self.test_balance
        account["last_reset_at"] = now
        account["equity_history"] = []
        self.account_states[self.account_mode] = account
        self.record_equity_point(note="Test balance baseline set", timestamp=now, persist=False, force=True)
        self.save_state()

    def add_active_trade(self, trade: Trade):
        self.active_trades[trade.symbol] = trade
        self.last_update = time.time()
        self.record_equity_point(note=f"{trade.symbol} opened", timestamp=trade.timestamp, persist=False)
        self.save_state()

    def close_trade(self, symbol: str, exit_price: float, exit_commission: float = 0.0):
        if symbol in self.active_trades:
            trade = self.active_trades.pop(symbol)
            trade.exit_price = exit_price
            trade.exit_timestamp = time.time()
            trade.status = "closed"
            trade.exit_commission = float(exit_commission or 0.0)
            trade.commission_paid = float(trade.entry_commission or 0.0) + trade.exit_commission
            trade.pnl = (exit_price - trade.entry_price) * trade.amount
            trade.net_pnl = trade.pnl - trade.commission_paid
            self.total_pnl += trade.pnl
            if self.test_balance is not None:
                self.test_balance += trade.pnl
            self.closed_trades.append(trade)
            self.last_update = time.time()
            self.record_equity_point(note=f"{trade.symbol} closed", timestamp=trade.exit_timestamp, persist=False, force=True)
            self.save_state()

    def set_activity(self, activity: str):
        self.current_activity = activity
        self.last_update = time.time()

    def add_log(self, message: str):
        safe_message = redact_sensitive_text(message)
        self.logs.append(f"{time.strftime('%H:%M:%S')} - {safe_message}")
        if len(self.logs) > 50:
            self.logs.pop(0)

    def _range_start(self, range_key: str):
        seconds = REPORT_RANGE_SECONDS.get(range_key, REPORT_RANGE_SECONDS["overall"])
        anchor = float(
            self.account_states[self.account_mode].get("last_reset_at")
            or self.account_states[self.account_mode].get("session_started_at")
            or self.start_time
            or time.time()
        )
        if seconds is None:
            return anchor
        return max(anchor, time.time() - seconds)

    def get_report_payload(self, range_key: str = "overall"):
        selected_range = range_key if range_key in REPORT_RANGE_SECONDS else "overall"
        self._rebuild_equity_history_if_missing()

        account = self.account_states[self.account_mode]
        report_start = self._range_start(selected_range)
        account_label = "Test Keys" if self.account_mode == "test" else "Real Keys"
        current_point = self._equity_point(note="Current equity")

        history = list(account.get("equity_history", []))
        prior_points = [point for point in history if point["timestamp"] < report_start]
        filtered_points = [point for point in history if point["timestamp"] >= report_start]
        if prior_points:
            baseline = dict(prior_points[-1])
            baseline["timestamp"] = report_start
            baseline["note"] = "Range start"
            filtered_points.insert(0, baseline)
        if not filtered_points:
            filtered_points = [{
                "timestamp": report_start,
                "equity": round(current_point["equity"], 8),
                "free_balance": round(current_point["free_balance"], 8),
                "allocated": round(current_point["allocated"], 8),
                "unrealized_pnl": round(current_point["unrealized_pnl"], 8),
                "realized_pnl": round(current_point["realized_pnl"], 8),
                "note": "Range start",
            }]
        if current_point["timestamp"] >= report_start:
            last_point = filtered_points[-1]
            if (
                abs(last_point["equity"] - current_point["equity"]) > 1e-9
                or abs(last_point["allocated"] - current_point["allocated"]) > 1e-9
                or abs(last_point["unrealized_pnl"] - current_point["unrealized_pnl"]) > 1e-9
            ):
                filtered_points.append(current_point)

        trades = []
        for trade in self.closed_trades:
            trade_time = float(trade.exit_timestamp or trade.timestamp or 0.0)
            if trade_time < report_start:
                continue
            trades.append({
                "symbol": trade.symbol,
                "entry_price": round(float(trade.entry_price), 8),
                "exit_price": round(float(trade.exit_price or 0.0), 8),
                "amount": round(float(trade.amount), 8),
                "opened_at": float(trade.timestamp),
                "closed_at": float(trade.exit_timestamp or trade.timestamp),
                "gross_pnl": round(float(trade.pnl or 0.0), 8),
                "commission_paid": round(float(trade.commission_paid or 0.0), 8),
                "net_pnl": round(float(trade.net_pnl if trade.net_pnl else trade.pnl - trade.commission_paid), 8),
                "status": trade.status,
                "stop_loss_price": round(float(trade.stop_loss_price or 0.0), 8),
                "hard_stop_price": round(float(trade.hard_stop_price or 0.0), 8),
                "profit_target_price": round(float(trade.profit_target_price or 0.0), 8),
                "quick_profit_price": round(float(trade.quick_profit_price or 0.0), 8),
                "high_water_price": round(float(trade.high_water_price or trade.entry_price), 8),
                "exit_reason": str(trade.exit_reason or ""),
            })
        trades.sort(key=lambda trade: trade["closed_at"], reverse=True)

        winning_trades = [trade for trade in trades if trade["net_pnl"] >= 0]
        losing_trades = [trade for trade in trades if trade["net_pnl"] < 0]
        total_net_pnl = sum(trade["net_pnl"] for trade in trades)
        total_gross_pnl = sum(trade["gross_pnl"] for trade in trades)
        total_commissions = sum(trade["commission_paid"] for trade in trades)
        start_equity = float(filtered_points[0]["equity"] if filtered_points else current_point["equity"])
        end_equity = float(filtered_points[-1]["equity"] if filtered_points else current_point["equity"])
        return_pct = ((end_equity - start_equity) / start_equity * 100.0) if start_equity else 0.0

        return {
            "account_mode": self.account_mode,
            "account_label": account_label,
            "range": selected_range,
            "generated_at": time.time(),
            "range_started_at": report_start,
            "session_started_at": float(account.get("session_started_at") or self.start_time or time.time()),
            "last_reset_at": float(account.get("last_reset_at") or self.start_time or time.time()),
            "quote_asset": self.quote_asset,
            "stats": {
                "trade_count": len(trades),
                "win_count": len(winning_trades),
                "loss_count": len(losing_trades),
                "win_rate": round((len(winning_trades) / len(trades) * 100.0) if trades else 0.0, 2),
                "gross_pnl": round(total_gross_pnl, 8),
                "net_pnl": round(total_net_pnl, 8),
                "commission_paid": round(total_commissions, 8),
                "start_equity": round(start_equity, 8),
                "end_equity": round(end_equity, 8),
                "return_pct": round(return_pct, 4),
                "best_trade": round(max((trade["net_pnl"] for trade in trades), default=0.0), 8),
                "worst_trade": round(min((trade["net_pnl"] for trade in trades), default=0.0), 8),
                "active_positions": len(self.active_trades),
            },
            "equity_curve": filtered_points,
            "trades": trades,
        }

    def to_dict(self):
        local_now = datetime.now().astimezone()
        total_unrealized = self._current_total_unrealized()
        total_allocated = self._current_total_allocated()
        if self.test_balance is not None:
            current_balance = self.test_balance
            free_balance = current_balance - total_allocated
        else:
            free_balance = self.balance
            current_balance = self.balance + total_allocated

        return {
            "user_email": self.user_email,
            "balance": current_balance,
            "free_balance": free_balance,
            "real_balance": self.balance,
            "quote_asset": self.quote_asset,
            "active_trades": {symbol: self._serialize_trade(trade) for symbol, trade in self.active_trades.items()},
            "closed_trades_count": len(self.closed_trades),
            "total_pnl": self.total_pnl + total_unrealized,
            "total_commission_paid": self.total_commission_paid,
            "current_activity": self.current_activity,
            "bot_running": self.bot_running,
            "bot_enabled": self.bot_enabled,
            "is_paper_trading": self.is_paper_trading,
            "account_mode": self.account_mode,
            "last_update": self.last_update,
            "start_time": self.start_time,
            "bot_clock": {
                "local_iso": local_now.isoformat(),
                "local_time": local_now.strftime("%I:%M:%S %p"),
                "timezone": local_now.tzname() or "Local",
                "utc_iso": datetime.now(timezone.utc).isoformat(),
            },
            "logs": self.logs,
            "recent_trades": [self._serialize_trade(trade) for trade in self.closed_trades[-5:]],
            "settings": {
                "mode": self.bot_mode,
                "risk": self.risk_percentage,
                "test_balance": self.test_balance,
                "account_mode": self.account_mode,
                "favorite_pairs_enabled": self.favorite_pairs_enabled,
                "favorite_pairs": list(self.favorite_pairs),
                "time_slots_enabled": self.time_slots_enabled,
                "time_slots": list(self.time_slots),
            }
        }


class _StateProxy:
    def __getattr__(self, name):
        return getattr(get_current_state(), name)

    def __setattr__(self, name, value):
        setattr(get_current_state(), name, value)


_default_state = BotState()
_state_context: ContextVar[Optional[BotState]] = ContextVar("bot_state_context", default=None)


def get_current_state():
    return _state_context.get() or _default_state


def set_current_state(current_state: BotState):
    _state_context.set(current_state)
    return current_state


state = _StateProxy()
