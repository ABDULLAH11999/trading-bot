import asyncio
import websockets
import json

async def test_ws():
    # Try different combinations
    urls = [
        "wss://testnet.binance.vision/stream?streams=btcusdt@kline_1m",
        "wss://testnet.binance.vision/ws/btcusdt@kline_1m",
    ]
    
    for url in urls:
        print(f"Testing URL: {url}")
        try:
            async with websockets.connect(url) as ws:
                print(f"Connected to {url}!")
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                print(f"Received data: {msg[:100]}")
                break
        except Exception as e:
            print(f"Failed {url}: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
