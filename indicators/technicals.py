import talib
import numpy as np
import pandas as pd

class TechnicalIndicators:
    @staticmethod
    def calculate_indicators(df, config):
        """
        Calculate technical indicators from a DataFrame of candles.
        df: columns -> open, high, low, close, volume, timestamp
        config: settings dictionary/object with RSI, MACD parameters
        """
        # Convert to numpy for TA-Lib
        close_prices = df['close'].values
        high_prices = df['high'].values
        low_prices = df['low'].values
        volumes = df['volume'].values
        
        # RSI
        df['rsi'] = talib.RSI(close_prices, timeperiod=config.RSI_PERIOD)
        
        # MACD
        macd, macdsignal, macdhist = talib.MACD(
            close_prices, 
            fastperiod=config.MACD_FAST, 
            slowperiod=config.MACD_SLOW, 
            signalperiod=config.MACD_SIGNAL
        )
        df['macd'] = macd
        df['macd_signal'] = macdsignal
        df['macd_hist'] = macdhist
        
        # EMA Crossover
        df['ema_9'] = talib.EMA(close_prices, timeperiod=config.EMA_SHORT)
        df['ema_21'] = talib.EMA(close_prices, timeperiod=config.EMA_LONG)
        df['ema_9_slope'] = df['ema_9'].pct_change().fillna(0.0)
        df['ema_21_slope'] = df['ema_21'].pct_change().fillna(0.0)
        
        # EMA Crossover Signal (for easier strategy logic)
        df['ema_cross'] = np.where(df['ema_9'] > df['ema_21'], 1, -1)
        
        # ATR Volatility
        df['atr'] = talib.ATR(high_prices, low_prices, close_prices, timeperiod=config.ATR_PERIOD)
        df['adx'] = talib.ADX(high_prices, low_prices, close_prices, timeperiod=14)
        
        # Volume Spike Detection
        df['avg_volume'] = df['volume'].rolling(window=20).mean()
        df['volume_spike'] = df['volume'] / df['avg_volume']
        
        # VWAP (Volume Weighted Average Price)
        # Assuming current session/day, we'll implement a simple rolling VWAP for intraday
        df['pv'] = df['close'] * df['volume']
        df['cumulative_pv'] = df['pv'].cumsum()
        df['cumulative_volume'] = df['volume'].cumsum()
        df['vwap'] = df['cumulative_pv'] / df['cumulative_volume']
        
        return df

    @staticmethod
    def calculate_orderbook_imbalance(orderbook):
        """
        Calculate orderbook pressure/imbalance.
        Ratio of (bids_volume / (bids_volume + asks_volume))
        """
        if not orderbook:
            return 0.5
            
        # Binance stream uses short keys b/a, REST-style uses bids/asks
        bids = orderbook.get('bids') or orderbook.get('b') or []
        asks = orderbook.get('asks') or orderbook.get('a') or []
        
        # We take the first few levels of the book for a faster scalping signal
        levels = 10
        bid_volume = sum(float(bid[1]) for bid in bids[:levels])
        ask_volume = sum(float(ask[1]) for ask in asks[:levels])
        
        if (bid_volume + ask_volume) == 0:
            return 0.5
            
        return bid_volume / (bid_volume + ask_volume)

    @staticmethod
    def calculate_orderbook_signal(orderbook, previous_signal=None):
        bids = orderbook.get('bids') or orderbook.get('b') or []
        asks = orderbook.get('asks') or orderbook.get('a') or []
        levels = 10

        bid_volume = sum(float(bid[1]) for bid in bids[:levels]) if bids else 0.0
        ask_volume = sum(float(ask[1]) for ask in asks[:levels]) if asks else 0.0
        top_bid_price = float(bids[0][0]) if bids else 0.0

        total_volume = bid_volume + ask_volume
        imbalance = (bid_volume / total_volume) if total_volume > 0 else 0.5

        previous_signal = previous_signal or {}
        previous_bid_volume = float(previous_signal.get("bid_volume", 0.0) or 0.0)
        previous_top_bid = float(previous_signal.get("top_bid_price", 0.0) or 0.0)

        bid_depth_growth = 1.0
        if previous_bid_volume > 0:
            bid_depth_growth = bid_volume / previous_bid_volume

        support_rising = (
            previous_bid_volume > 0
            and previous_top_bid > 0
            and top_bid_price >= previous_top_bid
            and bid_volume >= previous_bid_volume
        )

        return {
            "imbalance": imbalance,
            "bid_volume": bid_volume,
            "ask_volume": ask_volume,
            "top_bid_price": top_bid_price,
            "bid_depth_growth": bid_depth_growth,
            "support_rising": support_rising,
        }
    
