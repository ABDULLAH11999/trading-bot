import asyncio
import logging

from bot_state import set_current_state
from user_profiles import normalize_email

logger = logging.getLogger(__name__)
DEFAULT_RUNTIME_EMAIL = "__default__@local"


class MultiUserBotManager:
    def __init__(self, bot_factory):
        self.bot_factory = bot_factory
        self._bots = {}
        self._tasks = {}
        self._lock = asyncio.Lock()

    def _runtime_email(self, email):
        normalized = normalize_email(email)
        return normalized or DEFAULT_RUNTIME_EMAIL

    async def ensure_user_bot(self, email):
        runtime_email = self._runtime_email(email)

        async with self._lock:
            existing_bot = self._bots.get(runtime_email)
            existing_task = self._tasks.get(runtime_email)
            if existing_bot and existing_task and not existing_task.done():
                return existing_bot

            bot = self.bot_factory("" if runtime_email == DEFAULT_RUNTIME_EMAIL else runtime_email)
            self._bots[runtime_email] = bot
            set_current_state(bot.state)
            task = asyncio.create_task(bot.run(), name=f"bot:{runtime_email}")
            self._tasks[runtime_email] = task

            def _cleanup(done_task, user_key=runtime_email):
                try:
                    done_task.result()
                except asyncio.CancelledError:
                    logger.info("Bot task cancelled for %s", user_key)
                except Exception:
                    logger.exception("Bot task crashed for %s", user_key)

            task.add_done_callback(_cleanup)
            return bot

    async def get_state(self, email):
        bot = await self.ensure_user_bot(email)
        set_current_state(bot.state)
        return bot.state

    async def switch_account_mode(self, email, account_mode):
        bot = await self.ensure_user_bot(email)
        set_current_state(bot.state)
        return await bot.switch_account_mode(account_mode, user_email=email)

    async def update_user_preferences(self, email, preferences):
        bot = await self.ensure_user_bot(email)
        set_current_state(bot.state)
        return await bot.apply_user_preferences(preferences, log_change=True, refresh=True)

    async def get_pair_options(self, email):
        bot = await self.ensure_user_bot(email)
        set_current_state(bot.state)
        return await bot.get_pair_options()

    async def execute_manual_best_setup(self, email):
        bot = await self.ensure_user_bot(email)
        set_current_state(bot.state)
        return await bot.execute_manual_best_setup()

    async def get_chart_payload(self, email, symbol):
        bot = await self.ensure_user_bot(email)
        set_current_state(bot.state)
        return await bot.get_chart_payload(symbol)
