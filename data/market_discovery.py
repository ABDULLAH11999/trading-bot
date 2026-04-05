import asyncio
import logging
import math
import time

import aiohttp


logger = logging.getLogger(__name__)


class MarketDiscovery:
    def __init__(self, settings):
        self.settings = settings
        self.session = None
        self.exchange_cache = None
        self.ticker_cache = None
        self.profile_cache = {}

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _get_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=20)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def _get_json(self, url, params=None):
        session = await self._get_session()
        async with session.get(url, params=params, headers={"Accept": "application/json"}) as response:
            response.raise_for_status()
            return await response.json()

    async def fetch_exchange_info(self, force=False):
        if not force and self.exchange_cache and (time.time() - self.exchange_cache["ts"] < 600):
            return self.exchange_cache["data"]
        data = await self._get_json(f"{self.settings.PUBLIC_SPOT_API_URL}/api/v3/exchangeInfo")
        self.exchange_cache = {"ts": time.time(), "data": data}
        return data

    async def fetch_24h_tickers(self, force=False):
        if not force and self.ticker_cache and (time.time() - self.ticker_cache["ts"] < 120):
            return self.ticker_cache["data"]
        data = await self._get_json(f"{self.settings.PUBLIC_SPOT_API_URL}/api/v3/ticker/24hr")
        self.ticker_cache = {"ts": time.time(), "data": data}
        return data

    async def fetch_coin_profile(self, base_asset):
        asset = (base_asset or "").upper()
        cached = self.profile_cache.get(asset)
        if cached and (time.time() - cached["ts"] < self.settings.COINGECKO_CACHE_SECONDS):
            return cached["data"]

        default_profile = {
            "matched": False,
            "market_cap": 0.0,
            "circulating_supply": 0.0,
            "total_supply": 0.0,
            "source": "coingecko",
        }

        try:
            search = await self._get_json(
                f"{self.settings.COINGECKO_API_URL}/search",
                params={"query": asset},
            )
            matches = [
                coin for coin in search.get("coins", [])
                if coin.get("symbol", "").upper() == asset
            ]
            if not matches:
                self.profile_cache[asset] = {"ts": time.time(), "data": default_profile}
                return default_profile

            matches.sort(key=lambda coin: coin.get("market_cap_rank") or 10**9)
            coin_id = matches[0]["id"]
            markets = await self._get_json(
                f"{self.settings.COINGECKO_API_URL}/coins/markets",
                params={"vs_currency": "usd", "ids": coin_id, "sparkline": "false"},
            )
            if not markets:
                self.profile_cache[asset] = {"ts": time.time(), "data": default_profile}
                return default_profile

            market = markets[0]
            profile = {
                "matched": True,
                "market_cap": float(market.get("market_cap") or 0.0),
                "circulating_supply": float(market.get("circulating_supply") or 0.0),
                "total_supply": float(market.get("total_supply") or 0.0),
                "source": "coingecko",
            }
            self.profile_cache[asset] = {"ts": time.time(), "data": profile}
            return profile
        except Exception as exc:
            logger.warning("CoinGecko lookup failed for %s: %s", asset, exc)
            self.profile_cache[asset] = {"ts": time.time(), "data": default_profile}
            return default_profile

    def _is_supported_spot_symbol(self, symbol_info):
        symbol_name = symbol_info.get("symbol", "")
        if symbol_info.get("status") != "TRADING":
            return False
        if symbol_info.get("quoteAsset") != self.settings.QUOTE_ASSET:
            return False
        if not symbol_info.get("isSpotTradingAllowed", False):
            return False
        if any(flag in symbol_name for flag in ("UP", "DOWN", "BULL", "BEAR")):
            return False
        return True

    def _build_supported_symbol_snapshot(self, exchange_info, tickers):
        ticker_map = {item.get("symbol"): item for item in (tickers or [])}
        snapshot = {}
        for symbol_info in (exchange_info.get("symbols", []) or []):
            if not self._is_supported_spot_symbol(symbol_info):
                continue

            binance_symbol = symbol_info.get("symbol")
            ticker = ticker_map.get(binance_symbol)
            if not ticker:
                continue

            formatted_symbol = f"{symbol_info['baseAsset']}/{symbol_info['quoteAsset']}"
            snapshot[formatted_symbol] = {
                "symbol": formatted_symbol,
                "binance_symbol": binance_symbol,
                "base_asset": symbol_info["baseAsset"],
                "quote_asset": symbol_info["quoteAsset"],
                "price_change_pct": float(ticker.get("priceChangePercent") or 0.0),
                "quote_volume": float(ticker.get("quoteVolume") or 0.0),
                "trade_count": int(ticker.get("count") or 0),
                "onboard_date": int(symbol_info.get("onboardDate") or 0),
            }
        return snapshot

    async def fetch_supported_spot_snapshot(self, force=False):
        exchange_info, tickers = await asyncio.gather(
            self.fetch_exchange_info(force=force),
            self.fetch_24h_tickers(force=force),
        )
        return self._build_supported_symbol_snapshot(exchange_info, tickers)

    async def list_pair_options(self, major_symbols=None, limit=None):
        major_symbols = [str(symbol or "").strip().upper() for symbol in (major_symbols or []) if str(symbol or "").strip()]
        option_limit = max(1, int(limit or self.settings.FAVORITE_PAIR_OPTIONS_LIMIT))
        options = []
        seen = set()

        snapshot = {}
        try:
            snapshot = await self.fetch_supported_spot_snapshot()
        except Exception as exc:
            logger.warning("Static favorite pair options fallback active: %s", exc)

        for symbol in major_symbols[:option_limit]:
            item = snapshot.get(symbol)
            if symbol in seen:
                continue
            options.append({
                "symbol": symbol,
                "label": f"{symbol} ({float((item or {}).get('price_change_pct', 0.0) or 0.0):.2f}%)" if item else symbol,
                "group": "Major Pairs",
                "price_change_pct": float((item or {}).get("price_change_pct", 0.0) or 0.0),
                "quote_volume": float((item or {}).get("quote_volume", 0.0) or 0.0),
            })
            seen.add(symbol)

        top_gainers = sorted(
            snapshot.values(),
            key=lambda item: item.get("price_change_pct", 0.0),
            reverse=True,
        )[:option_limit]

        for item in top_gainers:
            symbol = item["symbol"]
            if symbol in seen:
                continue
            options.append({
                "symbol": symbol,
                "label": f"{symbol} ({item['price_change_pct']:.2f}%)",
                "group": "Top Gainers",
                "price_change_pct": item["price_change_pct"],
                "quote_volume": item["quote_volume"],
            })
            seen.add(symbol)

        return options

    def _base_score(self, age_days, gain_pct, quote_volume, trade_count):
        preferred_gain = self.settings.PREFERRED_DAILY_GAIN
        gain_alignment = max(0.0, 1.0 - (abs(gain_pct - preferred_gain) / max(preferred_gain, 1.0)))
        newness = max(0.0, 1.0 - (age_days / max(self.settings.NEW_LISTING_LOOKBACK_DAYS, 1)))
        volume_score = min(math.log10(max(quote_volume, 1.0)), 9.0) / 9.0
        trade_score = min(float(trade_count) / 10000.0, 1.0)
        return (gain_alignment * 40.0) + (newness * 30.0) + (volume_score * 20.0) + (trade_score * 10.0)

    def _passes_public_safety(self, candidate, profile):
        if candidate["quote_volume"] < self.settings.MIN_24H_QUOTE_VOLUME:
            return False, "24h quote volume below threshold"
        if candidate["trade_count"] < self.settings.MIN_TRADE_COUNT:
            return False, "Trade count below threshold"
        if candidate["price_change_pct"] > self.settings.MAX_DAILY_GAIN_TO_CHASE:
            return False, "Move too extended"
        if not profile.get("matched"):
            return False, "CoinGecko profile not matched"
        if profile["market_cap"] < self.settings.MIN_MARKET_CAP_USD:
            return False, "Market cap below threshold"
        if profile["circulating_supply"] < self.settings.MIN_CIRCULATING_SUPPLY:
            return False, "Circulating supply too low"
        return True, "Passed Binance spot and CoinGecko safety filters"

    async def discover_candidates(self):
        exchange_info, tickers = await asyncio.gather(
            self.fetch_exchange_info(),
            self.fetch_24h_tickers(),
        )
        ticker_map = {item.get("symbol"): item for item in tickers}
        now_ms = int(time.time() * 1000)

        prefiltered = []
        fallback = []
        for symbol_info in exchange_info.get("symbols", []):
            if not self._is_supported_spot_symbol(symbol_info):
                continue

            ticker = ticker_map.get(symbol_info.get("symbol"))
            if not ticker:
                continue

            price_change_pct = float(ticker.get("priceChangePercent") or 0.0)
            quote_volume = float(ticker.get("quoteVolume") or 0.0)
            trade_count = int(ticker.get("count") or 0)
            onboard_date = int(symbol_info.get("onboardDate") or 0)
            age_days = ((now_ms - onboard_date) / 86400000.0) if onboard_date else 9999.0

            candidate = {
                "symbol": f"{symbol_info['baseAsset']}/{symbol_info['quoteAsset']}",
                "binance_symbol": symbol_info["symbol"],
                "base_asset": symbol_info["baseAsset"],
                "quote_asset": symbol_info["quoteAsset"],
                "onboard_date": onboard_date,
                "age_days": age_days,
                "price_change_pct": price_change_pct,
                "quote_volume": quote_volume,
                "trade_count": trade_count,
            }

            if (
                age_days <= self.settings.NEW_LISTING_LOOKBACK_DAYS
                and self.settings.MIN_DAILY_GAIN <= price_change_pct <= self.settings.MAX_DAILY_GAIN_TO_CHASE
                and quote_volume >= self.settings.MIN_24H_QUOTE_VOLUME
            ):
                candidate["score"] = self._base_score(age_days, price_change_pct, quote_volume, trade_count)
                prefiltered.append(candidate)
            elif (
                self.settings.MIN_DAILY_GAIN <= price_change_pct <= self.settings.MAX_DAILY_GAIN_TO_CHASE
                and quote_volume >= self.settings.MIN_24H_QUOTE_VOLUME
            ):
                candidate["score"] = self._base_score(self.settings.NEW_LISTING_LOOKBACK_DAYS, price_change_pct, quote_volume, trade_count)
                fallback.append(candidate)

        prefiltered.sort(key=lambda item: item["score"], reverse=True)
        fallback.sort(key=lambda item: item["score"], reverse=True)
        shortlisted = (prefiltered + fallback)[: max(self.settings.UNIVERSE_SIZE * 2, 10)]

        results = []
        for candidate in shortlisted:
            profile = await self.fetch_coin_profile(candidate["base_asset"])
            safety_passed, safety_reason = self._passes_public_safety(candidate, profile)
            candidate["market_cap"] = profile.get("market_cap", 0.0)
            candidate["circulating_supply"] = profile.get("circulating_supply", 0.0)
            candidate["safety_passed"] = safety_passed
            candidate["safety_reason"] = safety_reason
            if safety_passed:
                results.append(candidate)

        results.sort(key=lambda item: item["score"], reverse=True)
        return results[: self.settings.UNIVERSE_SIZE]
