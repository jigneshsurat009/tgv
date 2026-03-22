from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.keyboards import (
    custom_final_picker,
    custom_position_picker,
    custom_strength_picker,
    custom_type_picker,
    intake_actions,
    mode_picker,
    per_item_picker,
    preset_picker,
    resume_menu,
    saved_presets_menu,
    select_videos,
)
from app.models import BatchMode, IntakeJob, JobStatus, MediaItem, PresetRule, SourceType
from app.services.google_auth import GoogleAuthError, GoogleDriveOAuth
from app.services.intake import scan_source
from app.services.link_parser import detect_source
from app.services.presets import build_saved_preset, builtin_presets
from app.services.processor import BatchProcessor
from app.services.state import JobState
from app.storage.db import Database
from app.utils.formatters import human_size
from app.utils.ids import new_id

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm"}
_custom_drafts: dict[int, dict] = {}


def build_router(settings: Settings, db: Database, state: JobState) -> Router:
    router = Router()
    processor = BatchProcessor(settings, db, state)
    google_oauth = GoogleDriveOAuth(settings.google_client_secret_file, settings.google_token_dir)

    def all_presets(user_id: int) -> list[PresetRule]:
        merged = builtin_presets(settings.watermark_text, settings.watermark_image)
        merged.extend(PresetRule.from_dict(row["payload"]) for row in db.list_presets(user_id))
        return merged

    def preset_map(user_id: int) -> dict[str, PresetRule]:
        return {p.preset_id: p for p in all_presets(user_id)}

    def parse_time_to_seconds(value: str) -> int:
        value = value.strip().upper()
        if value == "END":
            return -1
        parts = value.split(":")
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + int(s)
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + int(s)
        raise ValueError("Use mm:ss, hh:mm:ss, or END")

    def rule_from_range(user_id: int, start_s: int, end_s: int, watermark_type: str, position_mode: str, opacity: float) -> PresetRule:
        image_ok = watermark_type == "image" and bool(settings.watermark_image)
        actual_type = "image" if image_ok else "text"
        kwargs = dict(
            preset_id=new_id("preset"),
            name=f"Custom {start_s}s to {'END' if end_s < 0 else str(end_s)+'s'}",
            mode="full",
            watermark_type=actual_type,
            text=settings.watermark_text,
            image_path=settings.watermark_image if image_ok else "",
            position_mode=position_mode,
            opacity=opacity,
            scale=0.10 if position_mode in {"random_anywhere", "smooth_anywhere"} else 0.12,
            is_builtin=False,
        )
        if start_s <= 0 and end_s < 0:
            kwargs["mode"] = "full"
        elif start_s <= 0:
            kwargs["mode"] = "window"
            kwargs["start_at"] = 0
            kwargs["end_at"] = end_s
        elif end_s < 0:
            kwargs["mode"] = "after"
            kwargs["start_at"] = start_s
        else:
            kwargs["mode"] = "window"
            kwargs["start_at"] = start_s
            kwargs["end_at"] = end_s
        return PresetRule(**kwargs)

    @router.message(F.text == "/glogin")
    async def google_auth_start(message: Message) -> None:
        if not message.from_user:
            return
        try:
            auth_url = google_oauth.start_auth(message.from_user.id)
        except GoogleAuthError as exc:
            await message.answer(f"Google auth setup error: {exc}")
            return
        await message.answer(
            "Open this URL in a browser, approve access, then copy the FULL redirected localhost URL and send it back like this:\n\n"
            "/gauth http://localhost/?state=...&code=...\n\n"
            f"Auth URL:\n{auth_url}"
        )

    @router.message(F.text.startswith("/gauth "))
    async def google_auth_finish(message: Message) -> None:
        if not message.from_user or not message.text:
            return
        redirect_url = message.text.split(" ", 1)[1].strip()
        try:
            google_oauth.finish_auth_from_redirect(message.from_user.id, redirect_url)
        except GoogleAuthError as exc:
            await message.answer(f"Google auth failed: {exc}")
            return
        await message.answer("Google account linked. Now send /shared to browse Shared with me, or /shared <folder_id>.")

    @router.message(F.video | F.document)
    async def handle_upload(message: Message) -> None:
        media = message.video or message.document
        if not media or not message.from_user:
            return
        file_name = getattr(media, "file_name", None) or f"upload_{new_id('vid')}.mp4"
        mime = getattr(media, "mime_type", None)
        is_video = bool(message.video) or bool(mime and mime.startswith("video/")) or Path(file_name).suffix.lower() in VIDEO_EXTS
        if not is_video:
            await message.answer("Send or forward a video file.")
            return
        item = MediaItem(
            item_id=new_id("tg"),
            name=file_name,
            size_bytes=getattr(media, "file_size", 0) or 0,
            is_video=True,
            source_url="telegram://upload",
            mime_type=mime,
            telegram_file_id=media.file_id,
        )
        job = IntakeJob(
            job_id=new_id("job"),
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            source_type=SourceType.TELEGRAM_UPLOAD,
            source_value="telegram://upload",
            items=[item],
            selected_item_ids={item.item_id},
            created_at=datetime.utcnow().isoformat(),
        )
        state.save(job)
        await message.answer(
            f"Received 1 uploaded video\nSize: {human_size(item.size_bytes)}\n\nChoose action:",
            reply_markup=intake_actions(),
        )

    @router.message(F.text)
    async def handle_text(message: Message) -> None:
        if not message.text or not message.from_user:
            return
        user_id = message.from_user.id
        draft = _custom_drafts.get(user_id)
        if draft and draft.get("awaiting_range"):
            try:
                raw = message.text.replace("to", " ").replace("-", " ").split()
                if len(raw) == 1 and raw[0].lower() == "full":
                    start_s, end_s = 0, -1
                elif len(raw) == 2:
                    start_s = parse_time_to_seconds(raw[0])
                    end_s = parse_time_to_seconds(raw[1])
                    if end_s >= 0 and end_s <= start_s:
                        raise ValueError("End must be greater than start")
                else:
                    raise ValueError("Send: full OR start end. Example: 01:00 10:00 or 18:00 END")
            except Exception as exc:
                await message.answer(f"Invalid time range: {exc}")
                return
            draft["start_s"] = start_s
            draft["end_s"] = end_s
            draft["awaiting_range"] = False
            draft["rule"] = rule_from_range(user_id, start_s, end_s, draft["watermark_type"], draft["position_mode"], draft["opacity"])
            summary = (
                f"Custom watermark ready\n\n"
                f"Type: {draft['rule'].watermark_type}\n"
                f"Position: {draft['position_mode']}\n"
                f"Opacity: {draft['opacity']}\n"
                f"Time: {'FULL' if end_s < 0 and start_s <= 0 else f'{raw[0]} to {raw[1] if len(raw)>1 else 'END'}'}"
            )
            await message.answer(summary, reply_markup=custom_final_picker())
            return
        found = detect_source(message.text)
        if not found:
            return
        source_type, value = found
        try:
            items = await scan_source(source_type, value, user_id=message.from_user.id, settings=settings)
        except Exception as exc:
            await message.answer(f"Source scan failed: {exc}")
            return
        job = IntakeJob(
            job_id=new_id("job"),
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            source_type=source_type,
            source_value=value,
            items=items,
            created_at=datetime.utcnow().isoformat(),
        )
        state.save(job)
        total = sum(x.size_bytes for x in items)
        videos = [x for x in items if x.is_video]
        lines = [f"Found {len(items)} items", f"Videos: {len(videos)}", f"Total size: {human_size(total)}", ""]
        lines.extend([f"- {v.name} ({human_size(v.size_bytes)})" for v in videos[:10]])
        await message.answer("\n".join(lines), reply_markup=intake_actions() if videos else None)

    @router.callback_query(F.data == "menu:history")
    async def history_menu(callback: CallbackQuery) -> None:
        rows = db.list_history(callback.from_user.id)
        text = "No job history yet." if not rows else "\n".join([f"[{r['created_at']}] {r['event_type']} - {r['message']}" for r in rows])
        await callback.message.edit_text(text[:4000])
        await callback.answer()

    @router.callback_query(F.data == "menu:resume")
    async def resume_menu_cb(callback: CallbackQuery) -> None:
        row = db.get_failed_or_paused_job(callback.from_user.id)
        if not row:
            await callback.answer("No failed batch", show_alert=True)
            return
        await callback.message.edit_text(
            f"Resumable batch {row['job_id']}\nStatus: {row['status']}\nLast error: {row['last_error']}",
            reply_markup=resume_menu(row["job_id"]),
        )
        await callback.answer()

    @router.callback_query(F.data == "menu:presets")
    async def presets_menu(callback: CallbackQuery) -> None:
        await callback.message.edit_text("Save any built-in preset as your own reusable preset:", reply_markup=saved_presets_menu(builtin_presets(settings.watermark_text, settings.watermark_image)))
        await callback.answer()

    @router.callback_query(F.data.startswith("savepreset:"))
    async def save_preset(callback: CallbackQuery) -> None:
        source_id = callback.data.split(":", 1)[1]
        base = {x.preset_id: x for x in builtin_presets(settings.watermark_text, settings.watermark_image)}.get(source_id)
        if not base:
            await callback.answer("Preset not found", show_alert=True)
            return
        saved = build_saved_preset(f"My {base.name}", base)
        db.save_preset(callback.from_user.id, saved.preset_id, saved.name, saved.to_dict())
        await callback.answer("Preset saved")
        await callback.message.edit_text(f"Saved preset: {saved.name}\nUse it later in batch or per-video mode.")

    @router.callback_query(F.data == "action:cancel")
    async def cancel_job(callback: CallbackQuery) -> None:
        state.clear(callback.from_user.id)
        _custom_drafts.pop(callback.from_user.id, None)
        await callback.message.edit_text("Cancelled.")
        await callback.answer()

    @router.callback_query(F.data == "action:all")
    async def choose_all(callback: CallbackQuery) -> None:
        job = state.load(callback.from_user.id)
        if not job:
            await callback.answer("No active job", show_alert=True)
            return
        job.selected_item_ids = {x.item_id for x in job.items if x.is_video}
        state.save(job)
        await callback.message.edit_text("Choose processing mode:", reply_markup=mode_picker())
        await callback.answer()

    @router.callback_query(F.data == "action:none")
    async def no_mark(callback: CallbackQuery, bot: Bot) -> None:
        job = state.load(callback.from_user.id)
        if not job:
            await callback.answer("No active job", show_alert=True)
            return
        job.selected_item_ids = {x.item_id for x in job.items if x.is_video}
        job.batch_mode = BatchMode.NO_WATERMARK
        job.status = JobStatus.READY
        state.save(job)
        processor.checkpoint(job)
        await callback.message.edit_text("Processing selected videos without watermark...")
        await processor.process(callback.message, bot, job)
        await callback.answer()

    @router.callback_query(F.data == "action:select")
    async def select_mode(callback: CallbackQuery) -> None:
        job = state.load(callback.from_user.id)
        if not job:
            await callback.answer("No active job", show_alert=True)
            return
        await callback.message.edit_text("Select videos:", reply_markup=select_videos(job))
        await callback.answer()

    @router.callback_query(F.data.startswith("toggle:"))
    async def toggle_video(callback: CallbackQuery) -> None:
        job = state.load(callback.from_user.id)
        if not job:
            await callback.answer("No active job", show_alert=True)
            return
        item_id = callback.data.split(":", 1)[1]
        if item_id in job.selected_item_ids:
            job.selected_item_ids.remove(item_id)
        else:
            job.selected_item_ids.add(item_id)
        state.save(job)
        await callback.message.edit_reply_markup(reply_markup=select_videos(job))
        await callback.answer()

    @router.callback_query(F.data == "select:done")
    async def done_select(callback: CallbackQuery) -> None:
        job = state.load(callback.from_user.id)
        if not job or not job.selected_item_ids:
            await callback.answer("Select at least one video", show_alert=True)
            return
        await callback.message.edit_text("Choose processing mode:", reply_markup=mode_picker())
        await callback.answer()

    @router.callback_query(F.data == "mode:batch")
    async def mode_batch(callback: CallbackQuery) -> None:
        presets = all_presets(callback.from_user.id)
        await callback.message.edit_text("Choose one preset for all selected videos:", reply_markup=preset_picker("preset", presets))
        await callback.answer()

    @router.callback_query(F.data == "mode:preview")
    async def mode_preview(callback: CallbackQuery) -> None:
        presets = all_presets(callback.from_user.id)
        await callback.message.edit_text("Choose preview preset:", reply_markup=preset_picker("preview", presets))
        await callback.answer()

    @router.callback_query(F.data == "mode:peritem")
    async def mode_per_item(callback: CallbackQuery) -> None:
        job = state.load(callback.from_user.id)
        if not job:
            await callback.answer("No active job", show_alert=True)
            return
        if not job.per_item_presets:
            for item in job.selected_items():
                job.per_item_presets[item.item_id] = job.default_preset_id
            state.save(job)
        await callback.message.edit_text("Tap a video to assign its preset:", reply_markup=per_item_picker(job, preset_map(callback.from_user.id)))
        await callback.answer()

    @router.callback_query(F.data == "mode:custom")
    async def mode_custom(callback: CallbackQuery) -> None:
        job = state.load(callback.from_user.id)
        if not job or not job.selected_item_ids:
            await callback.answer("Select at least one video", show_alert=True)
            return
        _custom_drafts[callback.from_user.id] = {"job_id": job.job_id}
        await callback.message.edit_text("Choose watermark type for selected videos:", reply_markup=custom_type_picker())
        await callback.answer()

    @router.callback_query(F.data.startswith("ctype:"))
    async def custom_type(callback: CallbackQuery) -> None:
        draft = _custom_drafts.setdefault(callback.from_user.id, {})
        draft["watermark_type"] = callback.data.split(":", 1)[1]
        await callback.message.edit_text("Choose watermark position mode:", reply_markup=custom_position_picker())
        await callback.answer()

    @router.callback_query(F.data.startswith("cpos:"))
    async def custom_position(callback: CallbackQuery) -> None:
        draft = _custom_drafts.setdefault(callback.from_user.id, {})
        draft["position_mode"] = callback.data.split(":", 1)[1]
        await callback.message.edit_text("Choose watermark strength:", reply_markup=custom_strength_picker())
        await callback.answer()

    @router.callback_query(F.data.startswith("cop:"))
    async def custom_strength(callback: CallbackQuery) -> None:
        draft = _custom_drafts.setdefault(callback.from_user.id, {})
        draft["opacity"] = float(callback.data.split(":", 1)[1])
        draft["awaiting_range"] = True
        await callback.message.edit_text(
            "Send time range as text. Examples:\n"
            "full\n"
            "00:00 02:00\n"
            "01:00 10:00\n"
            "18:00 END"
        )
        await callback.answer()

    @router.callback_query(F.data == "custom:preview")
    async def custom_preview(callback: CallbackQuery, bot: Bot) -> None:
        draft = _custom_drafts.get(callback.from_user.id)
        job = state.load(callback.from_user.id)
        if not draft or not job or "rule" not in draft:
            await callback.answer("Finish custom setup first", show_alert=True)
            return
        rule = draft["rule"]
        job.default_preset_id = rule.preset_id
        job.batch_mode = BatchMode.PREVIEW_ONLY
        for item in job.selected_items():
            job.per_item_presets[item.item_id] = rule.preset_id
        db.save_preset(job.user_id, rule.preset_id, rule.name, rule.to_dict())
        state.save(job)
        processor.checkpoint(job)
        await callback.message.edit_text("Creating preview...")
        await processor.process(callback.message, bot, job, preview_only=True)
        await callback.answer()

    @router.callback_query(F.data.in_({"custom:apply", "custom:saveapply"}))
    async def custom_apply(callback: CallbackQuery, bot: Bot) -> None:
        draft = _custom_drafts.get(callback.from_user.id)
        job = state.load(callback.from_user.id)
        if not draft or not job or "rule" not in draft:
            await callback.answer("Finish custom setup first", show_alert=True)
            return
        rule = draft["rule"]
        if callback.data.endswith("saveapply"):
            saved = build_saved_preset(f"My {rule.name}", rule)
            db.save_preset(job.user_id, saved.preset_id, saved.name, saved.to_dict())
            rule = saved
        else:
            db.save_preset(job.user_id, rule.preset_id, rule.name, rule.to_dict())
        job.default_preset_id = rule.preset_id
        job.batch_mode = BatchMode.SAME_PRESET
        for item in job.selected_items():
            job.per_item_presets[item.item_id] = rule.preset_id
        job.status = JobStatus.READY
        state.save(job)
        processor.checkpoint(job)
        await callback.message.edit_text(f"Processing with custom rule: {rule.name}")
        await processor.process(callback.message, bot, job)
        _custom_drafts.pop(callback.from_user.id, None)
        await callback.answer()

    @router.callback_query(F.data.startswith("pickitem:"))
    async def pick_item(callback: CallbackQuery) -> None:
        item_id = callback.data.split(":", 1)[1]
        db.upsert_active_job(-callback.from_user.id, {"item_id": item_id})
        await callback.message.edit_text("Choose preset for this video:", reply_markup=preset_picker("itempreset", all_presets(callback.from_user.id)))
        await callback.answer()

    @router.callback_query(F.data.startswith("itempreset:"))
    async def item_preset(callback: CallbackQuery) -> None:
        picked = db.get_active_job(-callback.from_user.id) or {}
        item_id = picked.get("item_id")
        job = state.load(callback.from_user.id)
        if not item_id or not job:
            await callback.answer("Pick a video first", show_alert=True)
            return
        preset_id = callback.data.split(":", 1)[1]
        job.per_item_presets[item_id] = preset_id
        job.batch_mode = BatchMode.PER_VIDEO
        state.save(job)
        await callback.message.edit_text("Tap a video to assign its preset:", reply_markup=per_item_picker(job, preset_map(callback.from_user.id)))
        await callback.answer("Preset saved")

    @router.callback_query(F.data == "peritem:start")
    async def peritem_start(callback: CallbackQuery, bot: Bot) -> None:
        job = state.load(callback.from_user.id)
        if not job:
            await callback.answer("No active job", show_alert=True)
            return
        job.batch_mode = BatchMode.PER_VIDEO
        job.status = JobStatus.READY
        state.save(job)
        processor.checkpoint(job)
        await callback.message.edit_text("Processing selected videos with per-video presets...")
        await processor.process(callback.message, bot, job)
        await callback.answer()

    @router.callback_query(F.data.startswith("preset:"))
    async def apply_preset(callback: CallbackQuery, bot: Bot) -> None:
        job = state.load(callback.from_user.id)
        if not job:
            await callback.answer("No active job", show_alert=True)
            return
        preset_id = callback.data.split(":", 1)[1]
        job.default_preset_id = preset_id
        job.batch_mode = BatchMode.SAME_PRESET
        for item in job.selected_items():
            job.per_item_presets[item.item_id] = preset_id
        job.status = JobStatus.READY
        state.save(job)
        processor.checkpoint(job)
        label = preset_map(callback.from_user.id).get(preset_id, PresetRule(preset_id, preset_id, "full")).name
        await callback.message.edit_text(f"Processing with preset: {label}")
        await processor.process(callback.message, bot, job)
        await callback.answer()

    @router.callback_query(F.data.startswith("preview:"))
    async def apply_preview(callback: CallbackQuery, bot: Bot) -> None:
        job = state.load(callback.from_user.id)
        if not job:
            await callback.answer("No active job", show_alert=True)
            return
        preset_id = callback.data.split(":", 1)[1]
        job.default_preset_id = preset_id
        job.batch_mode = BatchMode.PREVIEW_ONLY
        for item in job.selected_items():
            job.per_item_presets[item.item_id] = preset_id
        job.status = JobStatus.READY
        state.save(job)
        processor.checkpoint(job)
        await callback.message.edit_text("Creating preview...")
        await processor.process(callback.message, bot, job, preview_only=True)
        await callback.answer()

    @router.callback_query(F.data.startswith("resume:"))
    async def resume_batch(callback: CallbackQuery, bot: Bot) -> None:
        job_id = callback.data.split(":", 1)[1]
        row = db.get_batch_job(job_id)
        if not row:
            await callback.answer("Batch not found", show_alert=True)
            return
        job = IntakeJob.from_dict(json.loads(row["payload"]))
        state.save(job)
        await callback.message.edit_text(f"Resuming failed batch {job_id}...")
        await processor.process(callback.message, bot, job, resume_failed_only=True)
        await callback.answer()

    return router
