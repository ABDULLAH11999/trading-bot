import ccxt

def test():
    exchange = ccxt.binance()
    exchange.set_sandbox_mode(True)
    try:
        print("Fetching exchange info (Sync)...")
        markets = exchange.load_markets()
        print(f"Success! Loaded {len(markets)} markets.")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test()
