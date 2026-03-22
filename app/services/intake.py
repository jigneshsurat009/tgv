from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.models import MediaItem, SourceType
from app.services.gdrive import GoogleDriveAdapter
from app.services.google_auth import GoogleDriveOAuth, GoogleAuthError
from app.services.mega_adapter import MegaAdapter
from app.utils.ids import new_id

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm"}
CACHE_ROOT = Path("./data/gdrive_cache")


async def scan_source(source_type: SourceType, value: str, *, user_id: int | None = None, settings: Settings | None = None) -> list[MediaItem]:
    settings = settings or Settings()
    if source_type == SourceType.TELEGRAM_UPLOAD:
        return []
    if source_type == SourceType.GDRIVE:
        adapter = GoogleDriveAdapter(CACHE_ROOT)
        return adapter.scan_public_link(value)
    if source_type == SourceType.GDRIVE_SHARED:
        if user_id is None:
            raise RuntimeError("User id is required for Google 'Shared with me' browsing.")
        oauth = GoogleDriveOAuth((settings.google_client_secret_file if settings else Path("./secrets/google_client_secret.json")), (settings.google_token_dir if settings else Path("./data/google_tokens")))
        folder_id = None if value == "oauth://shared-with-me" else value
        try:
            rows = oauth.list_shared_items(user_id, folder_id=folder_id)
        except GoogleAuthError as exc:
            raise RuntimeError(str(exc)) from exc
        items: list[MediaItem] = []
        for row in rows:
            is_folder = row.get("mimeType") == "application/vnd.google-apps.folder"
            name = row.get("name") or row.get("id") or "unnamed"
            if is_folder:
                display = f"[Folder] {name}"
                source_url = f"gdrive-shared-folder://{user_id}/{row['id']}"
                size = 0
            else:
                display = name
                source_url = f"gdrive-shared-file://{user_id}/{row['id']}"
                size = int(row.get("size") or 0)
            items.append(MediaItem(
                item_id=new_id("gshared"),
                name=display,
                size_bytes=size,
                is_video=(not is_folder and Path(name).suffix.lower() in VIDEO_EXTS),
                source_url=source_url,
                mime_type=row.get("mimeType"),
            ))
        return items
    if source_type == SourceType.MEGA:
        adapter = MegaAdapter(settings.mega_cache_dir if settings else Path("./data/mega_cache"))
        return adapter.scan_public_link(value)
    raise RuntimeError(f"Unsupported source type: {source_type}")
