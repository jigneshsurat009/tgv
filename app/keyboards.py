from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import IntakeJob, PresetRule


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Send / Forward Video", callback_data="noop")],
        [InlineKeyboardButton(text="Saved Presets", callback_data="menu:presets"), InlineKeyboardButton(text="Job History", callback_data="menu:history")],
        [InlineKeyboardButton(text="Resume Failed Batch", callback_data="menu:resume")],
    ])


def intake_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Watermark All Videos", callback_data="action:all")],
        [InlineKeyboardButton(text="Select Videos", callback_data="action:select")],
        [InlineKeyboardButton(text="Send Without Watermark", callback_data="action:none")],
        [InlineKeyboardButton(text="Cancel", callback_data="action:cancel")],
    ])


def select_videos(job: IntakeJob) -> InlineKeyboardMarkup:
    rows = []
    for item in job.items:
        if not item.is_video:
            continue
        checked = "✅" if item.item_id in job.selected_item_ids else "⬜"
        rows.append([InlineKeyboardButton(text=f"{checked} {item.name}", callback_data=f"toggle:{item.item_id}")])
    rows.append([InlineKeyboardButton(text="Done", callback_data="select:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mode_picker() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Apply Same Preset To All", callback_data="mode:batch")],
        [InlineKeyboardButton(text="Set Preset Per Video", callback_data="mode:peritem")],
        [InlineKeyboardButton(text="Manual Custom Time + Position", callback_data="mode:custom")],
        [InlineKeyboardButton(text="Preview First", callback_data="mode:preview")],
    ])


def preset_picker(prefix: str, presets: list[PresetRule]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=p.name, callback_data=f"{prefix}:{p.preset_id}")] for p in presets]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def per_item_picker(job: IntakeJob, presets_map: dict[str, PresetRule]) -> InlineKeyboardMarkup:
    rows = []
    for item in job.selected_items():
        pid = job.preset_id_for(item.item_id)
        label = presets_map.get(pid).name if pid in presets_map else pid
        rows.append([InlineKeyboardButton(text=f"{item.name} -> {label}", callback_data=f"pickitem:{item.item_id}")])
    rows.append([InlineKeyboardButton(text="Start Processing", callback_data="peritem:start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def saved_presets_menu(presets: list[PresetRule]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"Save {p.name}", callback_data=f"savepreset:{p.preset_id}")] for p in presets if p.mode != "none"]
    rows.append([InlineKeyboardButton(text="Back", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def resume_menu(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Resume Failed Items", callback_data=f"resume:{job_id}")]])


def custom_type_picker() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Text", callback_data="ctype:text"), InlineKeyboardButton(text="Logo/Image", callback_data="ctype:image")],
        [InlineKeyboardButton(text="Text + Logo (uses image if set)", callback_data="ctype:image")],
    ])


def custom_position_picker() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Bottom Right", callback_data="cpos:bottom_right"), InlineKeyboardButton(text="Center", callback_data="cpos:center")],
        [InlineKeyboardButton(text="Random Corners", callback_data="cpos:random_corners")],
        [InlineKeyboardButton(text="Random Anywhere", callback_data="cpos:random_anywhere")],
        [InlineKeyboardButton(text="Smooth Moving", callback_data="cpos:smooth_anywhere")],
    ])


def custom_strength_picker() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Light", callback_data="cop:0.12"), InlineKeyboardButton(text="Medium", callback_data="cop:0.18"), InlineKeyboardButton(text="Strong", callback_data="cop:0.28")],
    ])


def custom_final_picker() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Preview 20 sec", callback_data="custom:preview")],
        [InlineKeyboardButton(text="Apply To All Selected", callback_data="custom:apply")],
        [InlineKeyboardButton(text="Save As Preset + Apply", callback_data="custom:saveapply")],
    ])
