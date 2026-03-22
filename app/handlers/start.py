from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.keyboards import main_menu


router = Router()


@router.message(F.text == "/start")
async def start(message: Message) -> None:
    await message.answer(
        "Send or forward a video to start.\n\n"
        "Main features:\n"
        "- exact watermark range: full, 00:00 02:00, 01:00 10:00, 18:00 END\n"
        "- random anywhere position\n"
        "- smooth moving watermark\n"
        "- saved presets\n"
        "- apply same preset to all selected videos\n"
        "- per-video preset override\n"
        "- preview first\n"
        "- resume failed batch\n"
        "- job history\n"
        "- live progress bar during processing",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
