import asyncio
import websockets

async def test_ws():
    url = "wss://stream.testnet.binance.vision/stream?streams=btcusdt@kline_1m"
    print(f"Testing URL: {url}")
    try:
        async with websockets.connect(url) as ws:
            print(f"Connected to {url}!")
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            print(f"Received data: {msg[:100]}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
