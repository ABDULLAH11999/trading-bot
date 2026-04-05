import logging

logger = logging.getLogger(__name__)

class TradeExecutor:
    def __init__(self, exchange_client):
        self.exchange_client = exchange_client
        self.open_trades = [] # Keep locally, or manage via binance orders
        
    async def place_buy_market(self, symbol, amount, reference_price=None):
        logger.info(f"Placing market buy order for {symbol} of amount {amount}")
        order = await self.exchange_client.create_market_order(symbol, 'buy', amount, reference_price=reference_price)
        if order:
            logger.info(f"Market buy successful: {order.get('id', 'No ID')}")
            return order
        return None
        
    async def place_sell_market(self, symbol, amount, reference_price=None):
        logger.info(f"Placing market sell order for {symbol} of amount {amount}")
        order = await self.exchange_client.create_market_order(symbol, 'sell', amount, reference_price=reference_price)
        if order:
            logger.info(f"Market sell successful: {order.get('id', 'No ID')}")
            return order
        return None
    
    async def get_current_price(self, symbol):
        ticker = await self.exchange_client.fetch_ticker(symbol)
        return ticker.get('last', 0.0)
    
