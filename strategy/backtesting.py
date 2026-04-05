import pandas as pd
import numpy as np
import logging
from .config import settings
from .indicators.technicals import TechnicalIndicators
from .strategy.scalping_strategy import ScalpingStrategy
from .risk.risk_manager import RiskManager

logger = logging.getLogger(__name__)

class Backtester:
    def __init__(self):
        self.risk_manager = RiskManager(settings)
        self.technicals = TechnicalIndicators()
        self.strategy = ScalpingStrategy(self.risk_manager, self.technicals)
        self.balance = 1000.0  # Initial $1000
        self.active_trades = {}
        self.trade_history = []
        
    def run(self, symbol, data_file):
        """
        Run backtest on a CSV file of OHLCV data.
        """
        df = pd.read_csv(data_file)
        # Warmup indicators
        df = self.technicals.calculate_indicators(df, settings)
        
        for i in range(50, len(df)):
            current_row = df.iloc[i]
            prev_rows = df.iloc[:i+1].tail(100) # Window for indicators
            
            price = current_row['close']
            rsi = current_row['rsi']
            
            # --- EXIT CHECK ---
            if symbol in self.active_trades:
                trade = self.active_trades[symbol]
                
                # Check Stop Loss / Trailing Stop
                new_stop = self.risk_manager.update_trailing_stop(
                    price, trade['entry_price'], trade['stop_loss_price'], side='buy'
                )
                self.active_trades[symbol]['stop_loss_price'] = new_stop
                
                should_sell, reason = self.strategy.evaluate_sell(trade, price, rsi)
                if should_sell:
                    # Closing trade
                    exit_price = price
                    profit = (exit_price - trade['entry_price']) / trade['entry_price']
                    self.balance *= (1 + profit)
                    
                    self.trade_history.append({
                        'symbol': symbol,
                        'entry': trade['entry_price'],
                        'exit': exit_price,
                        'profit_pct': profit * 100,
                        'reason': reason,
                        'balance': self.balance
                    })
                    del self.active_trades[symbol]
                    self.risk_manager.current_trades -= 1
                    
            # --- ENTRY CHECK ---
            else:
                # In backtesting we might not have orderbook data, so we assume neutral or mock it
                imbalance = 0.65 # Assume favorable for testing strategy signals
                should_buy, reason = self.strategy.evaluate_buy(prev_rows, imbalance)
                
                if should_buy and self.risk_manager.current_trades < settings.MAX_SIMULTANEOUS_TRADES:
                    amount_to_risk = self.risk_manager.calculate_position_size(self.balance, price)
                    self.active_trades[symbol] = {
                        'entry_price': price,
                        'stop_loss_price': self.risk_manager.get_stop_loss_price(price),
                        'amount': amount_to_risk,
                        'rsi_at_entry': rsi
                    }
                    self.risk_manager.current_trades += 1
                    
        return self.generate_report()

    def generate_report(self):
        df_history = pd.DataFrame(self.trade_history)
        if df_history.empty:
            return "No trades executed."
            
        win_rate = (df_history['profit_pct'] > 0).mean() * 100
        total_profit = df_history['profit_pct'].sum()
        
        report = f"--- Backtest Report ---\n"
        report += f"Total Trades: {len(df_history)}\n"
        report += f"Win Rate: {win_rate:.2f}%\n"
        report += f"Cumulative Profit: {total_profit:.2f}%\n"
        report += f"Final Balance: ${self.balance:.2f}\n"
        return report

# Example usage when called directly
if __name__ == "__main__":
    # This is a placeholder as it requires real data files
    print("Backtester ready. Please provide a CSV with OHLCV data to run.")
    # tester = Backtester()
    # print(tester.run('BTC/USDT', 'data/btc_1m_historical.csv'))
    
