import os
import json
from pathlib import Path

from dotenv import load_dotenv
from user_profiles import get_profile, normalize_email

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = BASE_DIR / ".env"
APP_ENV_PATH = (os.getenv("APP_ENV_PATH") or "").strip()

env_candidates = []
if APP_ENV_PATH:
    env_candidates.append(Path(APP_ENV_PATH))
env_candidates.append(DEFAULT_ENV_FILE)
env_candidates.append(Path.cwd() / ".env")

resolved_env_file = None
for candidate in env_candidates:
    if candidate.exists():
        load_dotenv(candidate, override=False)
        resolved_env_file = candidate
        break

ENV_FILE = resolved_env_file or env_candidates[0]

# Binance credentials are stored per user profile. Legacy env keys are read only
# to help older installs migrate, but user-saved keys are the intended source.
LIVE_API_KEY = (os.getenv("BINANCE_API_KEY") or "").strip()
LIVE_API_SECRET = (os.getenv("BINANCE_API_SECRET") or "").strip()
TESTNET_API_KEY = (os.getenv("BINANCE_TESTNET_API_KEY") or "").strip()
TESTNET_API_SECRET = (os.getenv("BINANCE_TESTNET_API_SECRET") or "").strip()

paper_trading_env = os.getenv("PAPER_TRADING")
if paper_trading_env is None:
    PAPER_TRADING = True
else:
    PAPER_TRADING = paper_trading_env.lower() == "true"

DEFAULT_ACCOUNT_MODE = "test" if PAPER_TRADING else "real"
AUTH_SESSION_SECRET = (
    os.getenv("AUTH_SESSION_SECRET")
    or os.getenv("APP_ENCRYPTION_SECRET")
    or os.getenv("SECRET_KEY")
    or os.getenv("APP_PASSWORD")
    or "scalper-bot-session-secret"
).strip()
FORCE_SECURE_COOKIES = (os.getenv("FORCE_SECURE_COOKIES") or "").strip().lower() == "true"
ENABLE_API_DOCS = (os.getenv("ENABLE_API_DOCS") or "").strip().lower() == "true"
PUBLIC_APP_URL = (os.getenv("PUBLIC_APP_URL") or "").strip()
ADMIN_EMAIL = normalize_email(os.getenv("ADMIN_EMAIL"))
ADMIN_PASS = (os.getenv("ADMIN_PASS") or "").strip()
REAL_MODE_FEE = float((os.getenv("REAL_MODE_FEE") or "29").strip() or "29")


def _parse_allowed_emails(raw_value):
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return [normalize_email(item) for item in parsed if normalize_email(item)]
    except Exception:
        pass
    return [normalize_email(item) for item in raw_value.split(",") if normalize_email(item)]


def _parse_string_list(raw_value):
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except Exception:
        pass
    return [str(item).strip() for item in str(raw_value).split(",") if str(item).strip()]


CORS_ALLOWED_ORIGINS = _parse_string_list(os.getenv("CORS_ALLOWED_ORIGINS"))
APP_ALLOWED_HOSTS = _parse_string_list(os.getenv("APP_ALLOWED_HOSTS"))


def has_live_keys():
    return bool(LIVE_API_KEY and LIVE_API_SECRET)


def has_testnet_keys():
    return bool(TESTNET_API_KEY and TESTNET_API_SECRET)


def get_user_credentials(email, account_mode=None):
    normalized = normalize_email(email)
    mode = (account_mode or DEFAULT_ACCOUNT_MODE).strip().lower()
    profile = get_profile(normalized) if normalized else {"credentials": {"test": {}, "real": {}}}
    mode_credentials = (profile.get("credentials") or {}).get(mode, {}) or {}
    return {
        "account_mode": mode,
        "api_key": str(mode_credentials.get("api_key") or "").strip(),
        "api_secret": str(mode_credentials.get("api_secret") or "").strip(),
    }


def get_binance_credentials(account_mode=None, user_email=None):
    mode = (account_mode or DEFAULT_ACCOUNT_MODE).strip().lower()
    user_credentials = get_user_credentials(user_email, mode)
    if user_credentials["api_key"] and user_credentials["api_secret"]:
        if mode == "real":
            return {
                "account_mode": "real",
                "api_key": user_credentials["api_key"],
                "api_secret": user_credentials["api_secret"],
                "paper_trading": False,
                "credential_source": "user",
            }
        return {
            "account_mode": "test",
            "api_key": user_credentials["api_key"],
            "api_secret": user_credentials["api_secret"],
            "paper_trading": True,
            "credential_source": "user",
        }

    # Legacy fallback for older single-user installs. The app UI now prompts for
    # mode-specific keys before enabling trading.
    fallback_key = TESTNET_API_KEY if mode == "test" else LIVE_API_KEY
    fallback_secret = TESTNET_API_SECRET if mode == "test" else LIVE_API_SECRET
    return {
        "account_mode": "real" if mode == "real" else "test",
        "api_key": fallback_key,
        "api_secret": fallback_secret,
        "paper_trading": mode != "real",
        "credential_source": "env" if fallback_key and fallback_secret else "missing",
    }


def has_mode_credentials(account_mode, user_email=None):
    credentials = get_binance_credentials(account_mode, user_email=user_email)
    api_key = str(credentials.get("api_key") or "").strip()
    api_secret = str(credentials.get("api_secret") or "").strip()
    return bool(api_key and api_secret)


def mask_credential(value):
    credential = (value or "").strip()
    if not credential:
        return "(missing)"
    if len(credential) <= 8:
        return f"{credential[:2]}...{credential[-2:]}"
    return f"{credential[:4]}...{credential[-4:]}"


def runtime_config_summary(account_mode=None, user_email=None):
    credentials = get_binance_credentials(account_mode, user_email=user_email)
    return {
        "env_file": str(ENV_FILE),
        "default_account_mode": DEFAULT_ACCOUNT_MODE,
        "selected_account_mode": credentials["account_mode"],
        "paper_trading": credentials["paper_trading"],
        "api_key_masked": mask_credential(credentials["api_key"]),
        "has_live_keys": has_live_keys(),
        "has_testnet_keys": has_testnet_keys(),
        "credential_source": credentials.get("credential_source", "env"),
    }


def format_binance_auth_error(exc, account_mode, user_email=None):
    message = " ".join(str(exc).split())
    lowered = message.lower()
    if '"code":-2015' not in lowered and "invalid api-key" not in lowered:
        return message

    summary = runtime_config_summary(account_mode, user_email=user_email)
    mode_label = "real" if summary["selected_account_mode"] == "real" else "test"
    return (
        f"Binance rejected the {mode_label} API credentials "
        f"({summary['api_key_masked']}, source: {summary['credential_source']}, env: {summary['env_file']}). "
        "Error -2015 means the key/secret pair is not being accepted for this endpoint, "
        "or the source IP / API permissions no longer match the key settings in Binance."
    )


selected_credentials = get_binance_credentials(DEFAULT_ACCOUNT_MODE)
API_KEY = selected_credentials["api_key"]
API_SECRET = selected_credentials["api_secret"]

# Public market data sources that do not require API keys.
PUBLIC_SPOT_API_URL = "https://api.binance.com"
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"

# Trading configuration
QUOTE_ASSET = "USDT"
TRADING_SYMBOLS = [
    "DOGE/USDT",
    "PEPE/USDT",
    "SUI/USDT",
    "SEI/USDT",
]
MAJOR_SPOT_SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "DOGE/USDT",
    "LINK/USDT",
    "AVAX/USDT",
    "LTC/USDT",
    "TRX/USDT",
    "TON/USDT",
    "DOT/USDT",
    "MATIC/USDT",
    "SHIB/USDT",
    "BCH/USDT",
    "XLM/USDT",
    "ATOM/USDT",
    "NEAR/USDT",
    "UNI/USDT",
    "APT/USDT",
    "FIL/USDT",
    "ETC/USDT",
    "OP/USDT",
    "ARB/USDT",
    "INJ/USDT",
    "HBAR/USDT",
    "VET/USDT",
    "AAVE/USDT",
    "ALGO/USDT",
    "SUI/USDT",
    "SEI/USDT",
    "PEPE/USDT",
    "WIF/USDT",
    "FET/USDT",
    "RNDR/USDT",
    "GRT/USDT",
    "RUNE/USDT",
    "MKR/USDT",
    "SAND/USDT",
    "MANA/USDT",
    "CRV/USDT",
    "DYDX/USDT",
    "JUP/USDT",
    "TIA/USDT",
    "ICP/USDT",
    "EOS/USDT",
    "FLOW/USDT",
    "KAS/USDT",
    "JASMY/USDT",
]
FAVORITE_PAIR_OPTIONS_LIMIT = 50

# Dynamic Binance spot discovery
NEW_LISTING_LOOKBACK_DAYS = 21
UNIVERSE_SIZE = 8
UNIVERSE_REFRESH_SECONDS = 300
MIN_DAILY_GAIN = 8.0
PREFERRED_DAILY_GAIN = 25.0
MAX_DAILY_GAIN_TO_CHASE = 120.0
MIN_24H_QUOTE_VOLUME = 500000.0
MIN_TRADE_COUNT = 1500
MIN_MARKET_CAP_USD = 5000000.0
MIN_CIRCULATING_SUPPLY = 1000000.0
COINGECKO_CACHE_SECONDS = 21600

# Indicator parameters
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
EMA_SHORT = 9
EMA_LONG = 21
ATR_PERIOD = 14

# Strategy thresholds
RSI_BUY_MIN = 48
RSI_BUY_MAX = 78
RSI_SELL_THRESHOLD = 74
VOLUME_SPIKE_FACTOR = 1.3
BOOK_PRESSURE_THRESHOLD = 0.55
PROFIT_TARGET = 0.018
QUICK_PROFIT_TARGET = 0.010
MIN_HOLD_SECONDS = 120
STOP_LOSS_GRACE_SECONDS = 240
MAX_POSITION_HOLD_SECONDS = 1800
HTF_RSI_MIN = 52
ATR_MIN_PCT = 0.0025
ATR_MAX_PCT = 0.035
REGIME_MIN_ADX = 15
ENTRY_SCORE_THRESHOLD = 10
MIN_STOP_LOSS_PCT = 0.0075
MAX_STOP_LOSS_PCT = 0.010
MIN_REWARD_TO_RISK_RATIO = 1.55
TIME_DECAY_SECONDS = 720
TIME_DECAY_MIN_PROFIT = 0.002
BREAKEVEN_TRIGGER = 0.0045
BREAKEVEN_FEE_BUFFER = 0.0032
BREAKEVEN_MIN_HOLD_SECONDS = 120
PROTECTED_STOP_MIN_ARM_PCT = 0.0032
SECURE_PROFIT_TRIGGER_PCT = 0.006
SECURE_PROFIT_FLOOR_PCT = 0.0032
PROTECTED_STOP_MIN_PROFIT = 0.0075
RUNNER_MIN_PROFIT_PCT = 0.006
RUNNER_MAX_GIVEBACK_PCT = 0.007
RUNNER_EXTENDED_TARGET_MULTIPLIER = 1.6
RUNNER_RSI_FLOOR = 56
RUNNER_ORDERBOOK_IMBALANCE_MIN = 0.56
LOSS_STREAK_LIMIT = 3
CIRCUIT_BREAKER_DRAWDOWN_PCT = 0.02
CIRCUIT_BREAKER_COOLDOWN_SECONDS = 3600
SESSION_TARGET_PROFIT_PCT = 0.05
TRADING_DAY_START_HOUR_LOCAL = 8
NEGLIGIBLE_LOSS_PCT = 0.0035
PATIENCE_EXTENSION_SECONDS = 900
ENTRY_LOOKBACK_CANDLES = 5
ENTRY_ZONE_MAX = 0.58
ENTRY_PULLBACK_MIN = 0.0012
MIN_SHORT_MOMENTUM_PCT = 0.0034
MIN_IMPULSE_CANDLES = 2
MAX_RED_CANDLES_IN_PULLBACK = 1
MAX_PULLBACK_FROM_RECENT_HIGH_PCT = 0.03
MIN_CLOSE_TO_EMA9_RATIO = 0.9985
ENTRY_CONFIRMATIONS_REQUIRED = 3
ENTRY_CONFIRMATION_WINDOW_SECONDS = 120
BULLISH_WAVE_MIN_BODY_STRENGTH = 0.38
BULLISH_WAVE_MAX_WICK_RATIO = 0.45
BULLISH_WAVE_MAX_DISTANCE_FROM_HIGH = 0.0035
BULLISH_WAVE_MIN_RVOL = 1.0
BULLISH_WAVE_MIN_SHORT_MOMENTUM_PCT = 0.0018
MIN_ADX_TREND = 17
EMA_FAST_SLOPE_MIN = 0.00012
EMA_SLOW_SLOPE_MIN = 0.0
MOMENTUM_LOOKBACK_CANDLES = 5
MOMENTUM_LOOKBACK_MIN_PCT = 0.003
MOMENTUM_DIRECTIONAL_EFFICIENCY_MIN = 0.46
BREAKOUT_LOOKBACK_CANDLES = 6
BREAKOUT_CONFIRMATION_BUFFER = 0.9998
MIN_HTF_CONFIRM_POINTS = 3
MIN_HTF_CONFIRM_POINTS_FOR_LTF_OVERRIDE = 0
STRONG_LTF_OVERRIDE_MIN_POINTS = 3
STRONG_LTF_OVERRIDE_MIN_RVOL = 1.05
STRONG_LTF_OVERRIDE_MIN_SHORT_MOMENTUM_PCT = 0.0038
STRONG_LTF_OVERRIDE_MIN_DIRECTIONAL_EFFICIENCY = 0.52
STRONG_LTF_OVERRIDE_MIN_BODY_STRENGTH = 0.22
MIN_PROFIT_TARGET_PCT = 0.012
MIN_QUICK_PROFIT_TARGET_PCT = 0.0105
MIN_TRADEABLE_RANGE_PCT = 0.0012
MIN_UNIQUE_CLOSE_RATIO = 0.42
SHORT_TF_SIDEWAYS_RANGE_MAX_PCT = 0.004
SHORT_TF_SIDEWAYS_EFFICIENCY_MAX = 0.34
RESISTANCE_LOOKBACK_CANDLES = 18
RESISTANCE_NEAR_THRESHOLD_PCT = 0.003
RESISTANCE_BREAK_BUFFER = 1.0012
PULLBACK_RECOVERY_BUFFER = 1.0005
RECENT_RANGE_POSITION_MIN = 0.62
MAX_RECENT_LOWER_HIGHS = 2
MIN_HOLD_SECONDS_AFTER_ENTRY = 180
ENTRY_MAX_STRETCH_ABOVE_EMA9_PCT = 0.008
SMALL_RED_CANDLE_BODY_PCT = 0.0015
EXIT_CONFIRM_BEARISH_CANDLES = 2
PROFIT_PROTECTION_TRIGGER = 0.010
PROFIT_PROTECTION_FLOOR = 0.0032
RUNNER_BEARISH_EXIT_MIN_PROFIT = 0.003
SOFT_EXIT_ON_CANDLE_CLOSE_ONLY = True
MIN_HOLD_FOR_BEARISH_EXIT_SECONDS = 300
QUICK_REVERSAL_EXIT_MIN_SECONDS = 75
QUICK_REVERSAL_EXIT_MAX_PROFIT_PCT = 0.0025
QUICK_REVERSAL_EXIT_MAX_PEAK_PCT = 0.0035
MIN_PEAK_RETRACE_FOR_BEARISH_EXIT = 0.0025
INTRABAR_BREAKOUT_BUFFER = 1.0004
SIDEWAYS_TAKE_PROFIT_MIN_PCT = 0.004
SIDEWAYS_TAKE_PROFIT_RANGE_PCT = 0.0035
SIDEWAYS_TAKE_PROFIT_MIN_SECONDS = 150
POST_ENTRY_MOMENTUM_PATIENCE_SECONDS = 420
POST_ENTRY_STRUCTURE_HOLD_MAX_PULLBACK_PCT = 0.0045
CURRENT_HOUR_MANIPULATION_RANGE_PCT = 0.045
CURRENT_HOUR_MANIPULATION_RETRACE_PCT = 0.12
CURRENT_HOUR_MANIPULATION_CANDLE_PCT = 0.022
CURRENT_HOUR_MANIPULATION_EXTREME_WICK_RATIO = 0.58
CURRENT_HOUR_MANIPULATION_VOLUME_SPIKE = 2.8
CURRENT_HOUR_MANIPULATION_MIN_FLAGS = 2
ADAPTIVE_LOOKBACK_TRADES = 8
ADAPTIVE_MIN_WIN_RATE = 0.55
ADAPTIVE_MIN_AVG_PNL_PCT = 0.001
ADAPTIVE_ENTRY_CONFIRMATION_BONUS = 1
ADAPTIVE_BOOK_PRESSURE_BOOST = 0.03
ADAPTIVE_RSI_FLOOR_BOOST = 3
ADAPTIVE_MIN_SHORT_MOMENTUM_BOOST = 0.0008
ADAPTIVE_RVOL_BOOST = 0.15
ADAPTIVE_COOLDOWN_MINUTES = 2
SMALL_ACCOUNT_EQUITY_THRESHOLD = 150.0
SMALL_ACCOUNT_ENTRY_CONFIRMATION_BONUS = 1
SMALL_ACCOUNT_COOLDOWN_MULTIPLIER = 1.5

# Risk management
MAX_RISK_PER_TRADE = 0.01
STOP_LOSS = 0.06
HARD_STOP_LOSS = 0.010
TRAILING_STOP = 0.0038
TRAILING_START_PROFIT = 0.008
MAX_SIMULTANEOUS_TRADES = 2
COOLDOWN_MINUTES = 8
SIMULATED_COMMISSION_BASE = 0.001  # 0.1% normal fee per execution
SIMULATED_COMMISSION_HIGH = 0.002  # 0.2% during strong movement
SIMULATED_COMMISSION_EXTREME = 0.003  # 0.3% during extreme movement
SIMULATED_COMMISSION_MOVEMENT_LOOKBACK = 5
SIMULATED_COMMISSION_HIGH_MOVE_PCT = 0.18
SIMULATED_COMMISSION_EXTREME_MOVE_PCT = 0.30
SIMULATED_COMMISSION = SIMULATED_COMMISSION_BASE  # Backward-compatible alias
POSITION_SIZE_CAP = 0.98

# System settings
WS_URL = "wss://stream.binance.com:9443"
LOG_LEVEL = "INFO"
