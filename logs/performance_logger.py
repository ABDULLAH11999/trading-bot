import logging
import json
import os
import datetime

class PerformanceLogger:
    def __init__(self, log_dir='scalper_bot/logs'):
        self.log_dir = log_dir
        self.trade_log_path = os.path.join(self.log_dir, 'trades.json')
        
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
            
    def log_trade(self, trade_info):
        """
        Log complete trade information into JSON file for later analysis.
        """
        trade_entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'symbol': trade_info.get('symbol'),
            'side': trade_info.get('side'),
            'entry_price': trade_info.get('entry_price'),
            'exit_price': trade_info.get('exit_price'),
            'amount': trade_info.get('amount'),
            'profit_pct': trade_info.get('profit_pct'),
            'reason': trade_info.get('reason'),
            'rsi_at_entry': trade_info.get('rsi_at_entry')
        }
        
        # Load existing data
        data = []
        if os.path.exists(self.trade_log_path):
            with open(self.trade_log_path, 'r') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = []
                    
        data.append(trade_entry)
        
        # Save updated data
        with open(self.trade_log_path, 'w') as f:
            json.dump(data, f, indent=4)
            
    def get_summary(self):
        """Calculate and return key performance metrics."""
        if not os.path.exists(self.trade_log_path):
            return "No trades logged yet."
            
        with open(self.trade_log_path, 'r') as f:
            trades = json.load(f)
            
        if not trades:
            return "No trade history."
            
        total_trades = len(trades)
        wins = sum(1 for t in trades if t.get('profit_pct', 0) > 0)
        win_rate = (wins / total_trades) * 100
        avg_profit = sum(t.get('profit_pct', 0) for t in trades) / total_trades
        
        return {
            'total_trades': total_trades,
            'win_rate': f"{win_rate:.2f}%",
            'avg_profit_per_trade': f"{avg_profit:.2f}%"
        }
    
