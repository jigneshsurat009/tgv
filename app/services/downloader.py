from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot

from app.models import MediaItem, SourceType
from app.services.gdrive import GoogleDriveAdapter
from app.services.google_auth import GoogleDriveOAuth
from app.services.mega_adapter import MegaAdapter


async def download_item(item: MediaItem, source_type: SourceType, work_dir: Path, bot: Bot | None = None) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / item.name.replace("[Folder] ", "")
    if item.telegram_file_id and bot:
        file = await bot.get_file(item.telegram_file_id)
        await bot.download_file(file.file_path, destination=out_path)
        return out_path
    if source_type == SourceType.GDRIVE:
        adapter = GoogleDriveAdapter(Path("./data/gdrive_cache"))
        return adapter.fetch_to_workdir(item.source_url, item.name, work_dir)
    if source_type == SourceType.MEGA:
        adapter = MegaAdapter(Path("./data/mega_cache"))
        return adapter.fetch_to_workdir(item.source_url, item.name, work_dir)
    if source_type == SourceType.GDRIVE_SHARED:
        if item.source_url.startswith("gdrive-shared-file://"):
            payload = item.source_url.split("://", 1)[1]
            user_id_str, file_id = payload.split("/", 1)
            oauth = GoogleDriveOAuth(Path("./secrets/google_client_secret.json"), Path("./data/google_tokens"))
            return oauth.download_file(int(user_id_str), file_id, out_path)
        raise RuntimeError("Folders from Shared with me must be opened first using /shared <folder_id>.")
    parsed = urlparse(item.source_url)
    if parsed.scheme == "file":
        src = Path(parsed.path)
        out_path.write_bytes(src.read_bytes())
        return out_path
    raise RuntimeError("Unsupported download source.")
