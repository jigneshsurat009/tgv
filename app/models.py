from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    GDRIVE = "gdrive"
    MEGA = "mega"
    GDRIVE_SHARED = "gdrive_shared"
    TELEGRAM_UPLOAD = "telegram_upload"


class JobStatus(StrEnum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BatchMode(StrEnum):
    SAME_PRESET = "same_preset"
    PER_VIDEO = "per_video"
    NO_WATERMARK = "no_watermark"
    PREVIEW_ONLY = "preview_only"


class WatermarkPreset(StrEnum):
    FULL_FIXED = "full_fixed"
    FIRST_2_MIN = "first_2_min"
    AFTER_3_MIN = "after_3_min"
    LAST_2_MIN = "last_2_min"
    EVERY_3_MIN = "every_3_min"
    RANDOM_5 = "random_5"
    MIXED_SMART = "mixed_smart"
    NONE = "none"


@dataclass(slots=True)
class MediaItem:
    item_id: str
    name: str
    size_bytes: int
    is_video: bool
    source_url: str
    mime_type: str | None = None
    telegram_file_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaItem":
        return cls(**data)


@dataclass(slots=True)
class PresetRule:
    preset_id: str
    name: str
    mode: str
    watermark_type: str = "text"
    text: str = ""
    image_path: str = ""
    position_mode: str = "bottom_right"
    opacity: float = 0.18
    scale: float = 0.12
    start_at: int = 0
    end_at: int = 0
    repeat_every: int = 0
    show_for: int = 0
    random_count: int = 0
    moving: bool = False
    enabled: bool = True
    is_builtin: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PresetRule":
        return cls(**data)


@dataclass(slots=True)
class IntakeJob:
    job_id: str
    chat_id: int
    user_id: int
    source_type: SourceType
    source_value: str
    status: JobStatus = JobStatus.CREATED
    batch_mode: BatchMode = BatchMode.SAME_PRESET
    default_preset_id: str = WatermarkPreset.FULL_FIXED.value
    items: list[MediaItem] = field(default_factory=list)
    selected_item_ids: set[str] = field(default_factory=set)
    per_item_presets: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    last_error: str = ""

    def selected_items(self) -> list[MediaItem]:
        selected = self.selected_item_ids or {x.item_id for x in self.items if x.is_video}
        return [x for x in self.items if x.item_id in selected]

    def preset_id_for(self, item_id: str) -> str:
        if self.batch_mode == BatchMode.NO_WATERMARK:
            return WatermarkPreset.NONE.value
        return self.per_item_presets.get(item_id, self.default_preset_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "chat_id": self.chat_id,
            "user_id": self.user_id,
            "source_type": self.source_type.value,
            "source_value": self.source_value,
            "status": self.status.value,
            "batch_mode": self.batch_mode.value,
            "default_preset_id": self.default_preset_id,
            "items": [x.to_dict() for x in self.items],
            "selected_item_ids": sorted(self.selected_item_ids),
            "per_item_presets": self.per_item_presets,
            "created_at": self.created_at,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IntakeJob":
        return cls(
            job_id=data["job_id"],
            chat_id=data["chat_id"],
            user_id=data["user_id"],
            source_type=SourceType(data["source_type"]),
            source_value=data["source_value"],
            status=JobStatus(data.get("status", JobStatus.CREATED.value)),
            batch_mode=BatchMode(data.get("batch_mode", BatchMode.SAME_PRESET.value)),
            default_preset_id=data.get("default_preset_id", WatermarkPreset.FULL_FIXED.value),
            items=[MediaItem.from_dict(x) for x in data.get("items", [])],
            selected_item_ids=set(data.get("selected_item_ids", [])),
            per_item_presets=dict(data.get("per_item_presets", {})),
            created_at=data.get("created_at", ""),
            last_error=data.get("last_error", ""),
        )
