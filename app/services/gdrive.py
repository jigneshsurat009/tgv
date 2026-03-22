from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from urllib.parse import urlparse

import gdown

from app.models import MediaItem
from app.utils.ids import new_id

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm"}


class GoogleDriveError(RuntimeError):
    pass


class GoogleDriveAdapter:
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def _cache_dir(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        folder = self.cache_root / digest
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _is_folder_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return "/folders/" in parsed.path or "drive/folders" in url or "?id=" in parsed.query and "folders" in parsed.path

    def _media_item_from_path(self, path: Path, original_url: str) -> MediaItem:
        stat = path.stat()
        return MediaItem(
            item_id=new_id("item"),
            name=path.name,
            size_bytes=stat.st_size,
            is_video=path.suffix.lower() in VIDEO_EXTS,
            source_url=path.resolve().as_uri(),
            mime_type=None,
        )

    def scan_public_link(self, url: str) -> list[MediaItem]:
        cache_dir = self._cache_dir(url)
        try:
            if self._is_folder_url(url):
                downloaded = gdown.download_folder(url=url, output=str(cache_dir), quiet=True, remaining_ok=True, use_cookies=False)
                if not downloaded:
                    raise GoogleDriveError("Google Drive folder is empty, private, or could not be read.")
                items: list[MediaItem] = []
                for item_path in downloaded:
                    p = Path(item_path)
                    if p.is_file():
                        items.append(self._media_item_from_path(p, url))
                if not items:
                    raise GoogleDriveError("No downloadable files were found in that Drive folder.")
                return items

            downloaded = gdown.download(url=url, output=str(cache_dir), quiet=True, fuzzy=True, use_cookies=False)
            if not downloaded:
                raise GoogleDriveError("Google Drive file could not be downloaded. The link may be private or invalid.")
            p = Path(downloaded)
            if not p.is_file():
                raise GoogleDriveError("Downloaded Drive path is not a file.")
            return [self._media_item_from_path(p, url)]
        except Exception as exc:
            if isinstance(exc, GoogleDriveError):
                raise
            raise GoogleDriveError(f"Google Drive access failed: {exc}") from exc

    def fetch_to_workdir(self, source_url: str, file_name: str, work_dir: Path) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        parsed = urlparse(source_url)
        if parsed.scheme != "file":
            raise GoogleDriveError("Expected cached Drive file path.")
        src = Path(parsed.path)
        if not src.exists() or not src.is_file():
            raise GoogleDriveError("Cached Drive file no longer exists. Re-scan the Drive link and try again.")
        dest = work_dir / file_name
        if src.resolve() == dest.resolve():
            return dest
        shutil.copy2(src, dest)
        return dest
