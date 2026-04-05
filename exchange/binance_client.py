import logging
import time

import ccxt.async_support as ccxt
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BinanceClient:
    def __init__(self, api_key=None, api_secret=None, paper_trading=None, account_mode=None):
        credentials = settings.get_binance_credentials(account_mode)
        self.api_key = api_key if api_key is not None else credentials["api_key"]
        self.api_secret = api_secret if api_secret is not None else credentials["api_secret"]
        self.paper_trading = credentials["paper_trading"] if paper_trading is None else paper_trading
        self.account_mode = "test" if self.paper_trading else "real"

        self.public_exchange = ccxt.binance({
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
                "fetchMarkets": {"types": ["spot"]},
            },
        })

        self.exchange = ccxt.binance({
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
                "fetchMarkets": {"types": ["spot"]},
                "adjustForTimeDifference": True,
                "recvWindow": 10000,
            },
        })
        self._last_time_sync_at = 0.0
        self.last_order_error = None
        self.paper_mode_degraded = False
        if self.paper_trading:
            self.exchange.set_sandbox_mode(True)

    async def _sync_time_difference(self, force=False):
        now = time.time()
        if not force and (now - self._last_time_sync_at) < 60:
            return
        await self.exchange.load_time_difference()
        self._last_time_sync_at = now

    def _is_timestamp_error(self, exc):
        message = str(exc).lower()
        return (
            "timestamp for this request" in message
            or '"code":-1021' in message
            or "invalidnonce" in message
        )

    async def _call_private(self, operation, *args, **kwargs):
        await self._sync_time_difference()
        try:
            return await operation(*args, **kwargs)
        except Exception as exc:
            if not self._is_timestamp_error(exc):
                raise
            logger.warning("Binance time drift detected, resyncing and retrying request: %s", exc)
            await self._sync_time_difference(force=True)
            return await operation(*args, **kwargs)

    async def fetch_balance(self, asset="USDT"):
        if self.paper_trading and self.paper_mode_degraded:
            return 0.0
        balance_info = await self._call_private(self.exchange.fetch_balance)
        return balance_info.get(asset, {}).get("free", 0.0)

    async def fetch_balance_details(self):
        if self.paper_trading and self.paper_mode_degraded:
            return {}
        return await self._call_private(self.exchange.fetch_balance)

    async def fetch_ohlcv(self, symbol, timeframe="1m", limit=100):
        return await self.public_exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    async def fetch_ticker(self, symbol):
        return await self.public_exchange.fetch_ticker(symbol)

    async def fetch_tickers(self, symbols=None):
        return await self.public_exchange.fetch_tickers(symbols)

    def _collect_order_fees(self, order):
        fees = []
        if order.get("fees"):
            fees.extend(order.get("fees") or [])
        elif order.get("fee"):
            fees.append(order.get("fee"))
        else:
            for fill in ((order.get("info") or {}).get("fills") or []):
                fees.append({
                    "cost": fill.get("commission"),
                    "currency": fill.get("commissionAsset"),
                })
        return [fee for fee in fees if fee]

    def extract_net_filled_amount(self, order, symbol, fallback_amount=0.0):
        base_asset = symbol.split("/")[0]
        filled_amount = float(order.get("filled") or fallback_amount or 0.0)
        base_asset_fee = 0.0

        for fee in self._collect_order_fees(order):
            currency = str(fee.get("currency") or "").upper()
            cost = float(fee.get("cost") or 0.0)
            if currency == base_asset.upper():
                base_asset_fee += cost

        net_amount = max(0.0, filled_amount - base_asset_fee)
        return net_amount or filled_amount

    async def extract_commission_in_quote(self, order, symbol, reference_price=None, quote_asset="USDT"):
        base_asset, symbol_quote_asset = symbol.split("/")
        total_fee_in_quote = 0.0

        for fee in self._collect_order_fees(order):
            currency = str(fee.get("currency") or "").upper()
            cost = float(fee.get("cost") or 0.0)
            if cost <= 0:
                continue

            if currency in {symbol_quote_asset.upper(), quote_asset.upper()}:
                total_fee_in_quote += cost
                continue

            if currency == base_asset.upper() and reference_price:
                total_fee_in_quote += cost * float(reference_price)
                continue

            conversion_symbol = f"{currency}/{quote_asset.upper()}"
            try:
                await self.load_markets()
                if conversion_symbol in self.public_exchange.markets:
                    ticker = await self.fetch_ticker(conversion_symbol)
                    total_fee_in_quote += cost * float(ticker.get("last") or 0.0)
            except Exception as exc:
                logger.warning("Fee conversion lookup failed for %s: %s", conversion_symbol, exc)

        return total_fee_in_quote

    async def load_markets(self):
        if not self.public_exchange.markets:
            await self.public_exchange.load_markets()
        if self.paper_trading and self.paper_mode_degraded:
            return
        await self._sync_time_difference()
        if not self.exchange.markets:
            await self.exchange.load_markets()

    async def get_market_trade_rules(self, symbol, reference_price=None):
        await self.load_markets()
        market_source = self.public_exchange if (self.paper_trading and self.paper_mode_degraded) else self.exchange
        market = market_source.market(symbol)
        limits = market.get("limits", {})
        amount_limits = limits.get("amount", {}) or {}
        cost_limits = limits.get("cost", {}) or {}

        min_amount = float(amount_limits.get("min") or 0.0)
        min_cost = float(cost_limits.get("min") or 0.0)

        if min_cost <= 0 and reference_price and min_amount > 0:
            min_cost = min_amount * float(reference_price)

        return {
            "symbol": symbol,
            "min_amount": min_amount,
            "min_cost": min_cost,
            "precision_amount": market.get("precision", {}).get("amount"),
        }

    async def normalize_order_amount(
        self,
        symbol,
        amount,
        reference_price=None,
        enforce_min_cost=True,
        enforce_min_amount=True,
    ):
        await self.load_markets()
        market_source = self.public_exchange if (self.paper_trading and self.paper_mode_degraded) else self.exchange
        safe_amount = float(market_source.amount_to_precision(symbol, amount))
        rules = await self.get_market_trade_rules(symbol, reference_price=reference_price)

        if safe_amount <= 0:
            return None, "Calculated order quantity rounds to zero."

        if rules["min_amount"] and safe_amount < rules["min_amount"]:
            if not enforce_min_amount:
                return None, f"Available quantity {safe_amount} is below Binance minimum quantity {rules['min_amount']} for {symbol}."
            bumped_amount = float(market_source.amount_to_precision(symbol, rules["min_amount"]))
            if bumped_amount <= 0:
                return None, f"Exchange minimum quantity for {symbol} is {rules['min_amount']}."
            safe_amount = max(safe_amount, bumped_amount)

        if (
            enforce_min_cost
            and reference_price
            and rules["min_cost"]
            and (safe_amount * float(reference_price)) < rules["min_cost"]
        ):
            min_cost_amount = rules["min_cost"] / float(reference_price)
            safe_amount = float(market_source.amount_to_precision(symbol, min_cost_amount))
            if safe_amount * float(reference_price) < rules["min_cost"]:
                step = 10 ** -(rules["precision_amount"] or 8)
                safe_amount = float(market_source.amount_to_precision(symbol, safe_amount + step))

        if safe_amount <= 0:
            return None, "Calculated order quantity is invalid after exchange normalization."

        return safe_amount, None

    async def create_market_order(self, symbol, side, amount, reference_price=None):
        self.last_order_error = None
        try:
            safe_amount, error = await self.normalize_order_amount(
                symbol,
                amount,
                reference_price=reference_price,
                enforce_min_cost=(side.lower() == "buy"),
                enforce_min_amount=(side.lower() == "buy"),
            )
            if error:
                self.last_order_error = error
                logger.error("Order amount rejected for %s (%s): %s", symbol, side, error)
                return None
            if self.paper_trading and self.paper_mode_degraded:
                synthetic_price = float(reference_price or 0.0)
                if synthetic_price <= 0:
                    ticker = await self.fetch_ticker(symbol)
                    synthetic_price = float((ticker or {}).get("last") or (ticker or {}).get("close") or 0.0)
                if synthetic_price <= 0:
                    self.last_order_error = f"Could not derive a market price for paper order {symbol}."
                    return None
                timestamp_ms = int(time.time() * 1000)
                return {
                    "id": f"paper-{side}-{timestamp_ms}",
                    "symbol": symbol,
                    "side": side,
                    "type": "market",
                    "status": "closed",
                    "price": synthetic_price,
                    "average": synthetic_price,
                    "amount": safe_amount,
                    "filled": safe_amount,
                    "remaining": 0.0,
                    "cost": synthetic_price * safe_amount,
                    "fee": None,
                    "fees": [],
                    "timestamp": timestamp_ms,
                    "datetime": None,
                    "info": {"paper": True, "degraded": True},
                }
            return await self._call_private(self.exchange.create_market_order, symbol, side, safe_amount)
        except Exception as e:
            self.last_order_error = str(e)
            logger.error("Error creating market order for %s (%s): %s", symbol, side, e)
            return None

    async def create_limit_order(self, symbol, side, amount, price):
        try:
            return await self._call_private(self.exchange.create_order, symbol, "limit", side, amount, price)
        except Exception as e:
            logger.error("Error creating limit order for %s (%s): %s", symbol, side, e)
            return None

    async def fetch_open_orders(self, symbol=None):
        return await self._call_private(self.exchange.fetch_open_orders, symbol)

    async def cancel_order(self, order_id, symbol):
        return await self._call_private(self.exchange.cancel_order, order_id, symbol)

    async def close(self):
        await self.exchange.close()
        await self.public_exchange.close()
