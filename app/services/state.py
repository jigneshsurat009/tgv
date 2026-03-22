from __future__ import annotations

from app.models import IntakeJob
from app.storage.db import Database


class JobState:
    def __init__(self, db: Database):
        self.db = db

    def save(self, job: IntakeJob) -> None:
        self.db.upsert_active_job(job.user_id, job.to_dict())

    def load(self, user_id: int) -> IntakeJob | None:
        payload = self.db.get_active_job(user_id)
        return IntakeJob.from_dict(payload) if payload else None

    def clear(self, user_id: int) -> None:
        self.db.clear_active_job(user_id)
