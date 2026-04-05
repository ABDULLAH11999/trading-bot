import json
import asyncio
import logging
import websockets
from config.settings import WS_URL

logger = logging.getLogger(__name__)


class MarketStream:
    def __init__(self, symbols, on_candle_update, on_orderbook_update):
        self.symbols = list(symbols)
        self.on_candle_update = on_candle_update
        self.on_orderbook_update = on_orderbook_update
        self.ws = None
        self.symbol_version = 0
        self.pending_tasks = set()

    def update_symbols(self, symbols):
        normalized = list(dict.fromkeys(symbols))
        if normalized != self.symbols:
            self.symbols = normalized
            self.symbol_version += 1

    def _build_url(self):
        streams = []
        for sym in self.symbols:
            clean_sym = sym.replace("/", "").lower()
            streams.append(f"{clean_sym}@kline_1m")
            streams.append(f"{clean_sym}@depth10")

        stream_path = "/stream?streams=" + "/".join(streams)
        return f"{WS_URL}{stream_path}"

    def _track_task(self, coro):
        task = asyncio.create_task(coro)
        self.pending_tasks.add(task)

        def _cleanup(done_task):
            self.pending_tasks.discard(done_task)
            try:
                done_task.result()
            except Exception as exc:
                logger.error("Stream callback task failed: %s", exc)

        task.add_done_callback(_cleanup)

    async def connect(self):
        while True:
            if not self.symbols:
                await asyncio.sleep(2)
                continue

            version = self.symbol_version
            full_url = self._build_url()
            logger.info("Connecting to websocket: %s", full_url)

            try:
                async with websockets.connect(full_url, ping_interval=20, ping_timeout=20) as ws:
                    self.ws = ws
                    logger.info("Websocket connected.")
                    while True:
                        if version != self.symbol_version:
                            logger.info("Trading universe changed. Reconnecting websocket streams.")
                            await ws.close()
                            break

                        message = await asyncio.wait_for(ws.recv(), timeout=45)
                        data = json.loads(message)
                        stream_name = data.get("stream", "")
                        payload = data.get("data", {})

                        if "@kline" in stream_name:
                            self._track_task(self.on_candle_update(payload, stream_name))
                        elif "@depth" in stream_name:
                            self._track_task(self.on_orderbook_update(payload, stream_name))
            except asyncio.TimeoutError:
                logger.warning("Websocket stalled. Reconnecting in 3s...")
                self.ws = None
                await asyncio.sleep(3)
            except Exception as e:
                logger.error("Websocket error: %s. Reconnecting in 3s...", e)
                self.ws = None
                await asyncio.sleep(3)

    async def disconnect(self):
        for task in list(self.pending_tasks):
            task.cancel()
        if self.pending_tasks:
            await asyncio.gather(*self.pending_tasks, return_exceptions=True)
        if self.ws:
            await self.ws.close()
