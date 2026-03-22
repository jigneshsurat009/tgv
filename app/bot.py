from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.config import Settings
from app.handlers.jobs import build_router
from app.handlers.start import router as start_router
from app.services.state import JobState
from app.storage.db import Database


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    settings.ensure_dirs()
    db = Database(settings.data_dir / "bot.sqlite3")
    state = JobState(db)
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(build_router(settings, db, state))
    asyncio.run(dp.start_polling(bot))
