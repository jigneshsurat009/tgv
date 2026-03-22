from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, Message

from app.config import Settings
from app.models import IntakeJob, JobStatus, PresetRule
from app.services.downloader import download_item
from app.services.presets import builtin_presets
from app.services.state import JobState
from app.services.watermark import preview_clip, watermark_video
from app.storage.db import Database

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm"}


def _bar(percent: float, width: int = 16) -> str:
    done = max(0, min(width, round(width * percent / 100)))
    return "[" + "█" * done + "░" * (width - done) + "]"


class BatchProcessor:
    def __init__(self, settings: Settings, db: Database, state: JobState):
        self.settings = settings
        self.db = db
        self.state = state

    def _rule_map(self, user_id: int) -> dict[str, PresetRule]:
        mapping = {x.preset_id: x for x in builtin_presets(self.settings.watermark_text, self.settings.watermark_image)}
        for row in self.db.list_presets(user_id):
            mapping[row["preset_id"]] = PresetRule.from_dict(row["payload"])
        return mapping

    def checkpoint(self, job: IntakeJob) -> None:
        item_rows = []
        for item in job.selected_items():
            item_rows.append({
                "job_id": job.job_id,
                "item_id": item.item_id,
                "item_name": item.name,
                "source_url": item.source_url,
                "preset_id": job.preset_id_for(item.item_id),
                "status": "pending",
                "step": "queued",
                "error": "",
                "output_path": "",
                "attempts": 0,
            })
        self.db.create_batch_job(job.to_dict(), item_rows, job.last_error)
        self.db.add_history(job.job_id, job.user_id, "checkpoint", f"Checkpointed {len(item_rows)} selected videos")

    async def _safe_edit(self, msg: Message, text: str) -> None:
        try:
            await msg.edit_text(text)
        except Exception:
            pass

    async def process(self, message: Message, bot: Bot, job: IntakeJob, *, preview_only: bool = False, resume_failed_only: bool = False) -> None:
        selected = job.selected_items()
        if not selected:
            await message.answer("No videos selected.")
            return
        rules = self._rule_map(job.user_id)
        work_dir = self.settings.temp_dir / job.job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        status_msg = await message.answer("Preparing batch...")
        job.status = JobStatus.RUNNING
        self.state.save(job)
        self.db.update_batch_status(job.job_id, job.status.value, job.to_dict())
        items_state = {row["item_id"]: row for row in self.db.get_batch_items(job.job_id)}
        try:
            for idx, item in enumerate(selected, start=1):
                state_row = items_state.get(item.item_id)
                if resume_failed_only and state_row and state_row["status"] == "completed":
                    continue
                attempts = int((state_row or {}).get("attempts", 0)) + 1
                self.db.update_batch_item(job.job_id, item.item_id, status="running", step="download", attempts=attempts)
                await self._safe_edit(status_msg, f"{idx}/{len(selected)} {item.name}\n\nStage: Downloading\n{_bar(5)} 5%")
                input_path = await download_item(item, job.source_type, work_dir, bot=bot)
                final_path = input_path
                preset_id = job.preset_id_for(item.item_id)
                rule = rules.get(preset_id) or rules["full_fixed"]
                suffix = Path(item.name).suffix.lower()

                async def update_progress(stage: str, percent: float, current: str, total: str) -> None:
                    base = 25 + percent * 0.6 if stage in {"Preview", "Watermarking"} else percent
                    await self._safe_edit(
                        status_msg,
                        f"{idx}/{len(selected)} {item.name}\n\n"
                        f"Preset: {rule.name}\n"
                        f"Stage: {stage}\n"
                        f"{_bar(base)} {int(base)}%\n"
                        f"Time: {current} / {total}",
                    )

                if preview_only:
                    preview_path = work_dir / f"preview_{Path(item.name).stem}.mp4"
                    self.db.update_batch_item(job.job_id, item.item_id, status="running", step="preview")
                    await preview_clip(self.settings.ffmpeg_bin, self.settings.ffprobe_bin, input_path, preview_path, progress_cb=update_progress)
                    if rule.mode != "none" and suffix in VIDEO_EXTS:
                        preview_wm = work_dir / f"preview_wm_{Path(item.name).stem}.mp4"
                        await watermark_video(self.settings.ffmpeg_bin, self.settings.ffprobe_bin, preview_path, preview_wm, rule, progress_cb=update_progress)
                        final_path = preview_wm
                    else:
                        final_path = preview_path
                    await self._safe_edit(status_msg, f"{idx}/{len(selected)} {item.name}\n\nStage: Uploading\n{_bar(92)} 92%")
                    await message.answer_document(FSInputFile(final_path), caption=f"Preview: {item.name} [{rule.name}]")
                    self.db.update_batch_item(job.job_id, item.item_id, status="completed", step="preview_sent", output_path=str(final_path))
                    self.db.add_history(job.job_id, job.user_id, "preview", f"Preview sent for {item.name}")
                    break
                else:
                    if rule.mode != "none" and suffix in VIDEO_EXTS:
                        output_path = work_dir / f"wm_{Path(item.name).stem}.mp4"
                        self.db.update_batch_item(job.job_id, item.item_id, status="running", step="watermark")
                        await watermark_video(self.settings.ffmpeg_bin, self.settings.ffprobe_bin, input_path, output_path, rule, progress_cb=update_progress)
                        final_path = output_path
                    await self._safe_edit(status_msg, f"{idx}/{len(selected)} {item.name}\n\nStage: Uploading\n{_bar(92)} 92%")
                    self.db.update_batch_item(job.job_id, item.item_id, status="running", step="upload", output_path=str(final_path), attempts=attempts)
                    await message.answer_document(FSInputFile(final_path), caption=f"Done: {item.name} [{rule.name}]")
                    self.db.update_batch_item(job.job_id, item.item_id, status="completed", step="sent", output_path=str(final_path), attempts=attempts)
                    self.db.add_history(job.job_id, job.user_id, "item_completed", f"Completed {item.name} using {rule.name}")
                    await self._safe_edit(status_msg, f"{idx}/{len(selected)} {item.name}\n\nStage: Completed\n{_bar(100)} 100%")
            job.status = JobStatus.COMPLETED if not preview_only else JobStatus.PAUSED
            self.db.update_batch_status(job.job_id, job.status.value, job.to_dict())
            self.db.add_history(job.job_id, job.user_id, job.status.value, f"Job {job.job_id} is {job.status.value}")
            if job.status == JobStatus.COMPLETED:
                self.state.clear(job.user_id)
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.last_error = str(exc)
            self.state.save(job)
            self.db.update_batch_status(job.job_id, job.status.value, job.to_dict(), last_error=job.last_error)
            self.db.add_history(job.job_id, job.user_id, "failed", f"Failed: {job.last_error}")
            await self._safe_edit(status_msg, f"Failed on {item.name if 'item' in locals() else 'job'}\n\n{job.last_error[:3500]}")
            raise
        finally:
            if job.status == JobStatus.COMPLETED:
                try:
                    shutil.rmtree(work_dir, ignore_errors=True)
                except Exception:
                    pass
