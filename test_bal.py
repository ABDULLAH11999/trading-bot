import asyncio
import ccxt.async_support as ccxt

async def test():
    exchange = ccxt.binance({
        'options': {'defaultType': 'spot'}
    })
    exchange.set_sandbox_mode(True)
    try:
        print("Fetching balance...")
        markets = await exchange.load_markets()
        print("Success!", len(markets))
    except Exception as e:
        print(f"Failed: {type(e).__name__}: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test())
