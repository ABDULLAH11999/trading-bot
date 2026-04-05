import asyncio
import ccxt.async_support as ccxt

async def test():
    exchange = ccxt.binance()
    exchange.set_sandbox_mode(True)
    try:
        print("Fetching exchange info...")
        markets = await exchange.load_markets()
        print(f"Success! Loaded {len(markets)} markets.")
    except Exception as e:
        print(f"Failed: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test())
