import logging

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, settings):
        self.settings = settings
        self.max_trades = settings.MAX_SIMULTANEOUS_TRADES
        self.current_trades = 0
        self.cooldown_periods = {}

    def record_trade_execution(self, symbol, executed_at=None):
        self.cooldown_periods[symbol] = float(executed_at or 0)

    def check_new_trade_allowance(self, symbol, current_timestamp=0, cooldown_minutes=None, active_trade_count=None):
        open_trades = self.current_trades if active_trade_count is None else int(active_trade_count)
        if open_trades >= self.max_trades:
            return False, "Maximum simultaneous trades reached."

        last_traded = self.cooldown_periods.get(symbol, 0)
        cooldown_window = self.settings.COOLDOWN_MINUTES if cooldown_minutes is None else cooldown_minutes
        cooldown_seconds = max(0.0, float(cooldown_window)) * 60
        if current_timestamp - last_traded < cooldown_seconds:
            return False, f"Cooldown active for {symbol}."

        return True, "Trade allowed."

    def calculate_position_size(self, balance, current_price, custom_risk=None, custom_sl=None):
        risk_pct = custom_risk if custom_risk is not None else self.settings.MAX_RISK_PER_TRADE

        risk_pct = max(0.0, min(float(risk_pct), 1.0))
        position_cap = max(0.0, min(float(getattr(self.settings, "POSITION_SIZE_CAP", 0.98)), 1.0))
        risk_budget = balance * risk_pct
        stop_pct = max(float(custom_sl or 0.0), 0.0)
        if current_price > 0 and stop_pct > 0:
            position_value = risk_budget / stop_pct
        else:
            position_value = balance * risk_pct
        position_value = min(position_value, balance * position_cap)
        return position_value / current_price if current_price > 0 else 0.0

    def get_stop_loss_price(self, entry_price, side="buy", custom_sl=None):
        stop_pct = custom_sl if custom_sl is not None else self.settings.STOP_LOSS
        if side == "buy":
            return entry_price * (1 - stop_pct)
        return entry_price * (1 + stop_pct)

    def get_take_profit_price(self, entry_price, side="buy", custom_tp=None):
        profit_pct = custom_tp if custom_tp is not None else self.settings.PROFIT_TARGET
        if side == "buy":
            return entry_price * (1 + profit_pct)
        return entry_price * (1 - profit_pct)

    def update_trailing_stop(self, current_price, last_stop_price, custom_trail=None, side="buy"):
        trail_pct = custom_trail if custom_trail is not None else self.settings.TRAILING_STOP
        trail_pct = max(float(trail_pct), 0.001)

        if side == "buy":
            new_stop = current_price * (1 - trail_pct)
            if new_stop > last_stop_price:
                return new_stop
        else:
            new_stop = current_price * (1 + trail_pct)
            if new_stop < last_stop_price:
                return new_stop

        return last_stop_price
