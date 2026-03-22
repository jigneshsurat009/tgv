from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from urllib.parse import urlparse

from app.models import MediaItem
from app.utils.ids import new_id

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm"}


class MegaError(RuntimeError):
    pass


class MegaAdapter:
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def _cache_dir(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        folder = self.cache_root / digest
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _load_client(self):
        try:
            from mega import Mega  # type: ignore
        except Exception as exc:
            raise MegaError(
                "mega.py is not installed correctly. Run: pip install mega.py"
            ) from exc
        return Mega()

    def _download_public(self, url: str, out_dir: Path) -> list[Path]:
        mega = self._load_client()
        try:
            before = {p.resolve() for p in out_dir.rglob('*') if p.is_file()}
            result = mega.download_url(url, dest_path=str(out_dir))
            paths: list[Path] = []
            if isinstance(result, str):
                p = Path(result)
                if p.exists() and p.is_file():
                    paths.append(p)
            after = [p for p in out_dir.rglob('*') if p.is_file() and p.resolve() not in before]
            for p in after:
                if p not in paths:
                    paths.append(p)
            return paths
        except Exception as exc:
            raise MegaError(f"MEGA download failed: {exc}") from exc

    def scan_public_link(self, url: str) -> list[MediaItem]:
        cache_dir = self._cache_dir(url)
        files = [p for p in cache_dir.rglob('*') if p.is_file()]
        if not files:
            files = self._download_public(url, cache_dir)
        if not files:
            raise MegaError("No downloadable files were found in that MEGA link.")
        items: list[MediaItem] = []
        for path in files:
            stat = path.stat()
            items.append(MediaItem(
                item_id=new_id("mega"),
                name=path.name,
                size_bytes=stat.st_size,
                is_video=path.suffix.lower() in VIDEO_EXTS,
                source_url=path.resolve().as_uri(),
                mime_type=None,
            ))
        return items

    def fetch_to_workdir(self, source_url: str, file_name: str, work_dir: Path) -> Path:
        parsed = urlparse(source_url)
        if parsed.scheme != 'file':
            raise MegaError("Expected cached MEGA file path.")
        src = Path(parsed.path)
        if not src.exists() or not src.is_file():
            raise MegaError("Cached MEGA file no longer exists. Re-scan the MEGA link and try again.")
        work_dir.mkdir(parents=True, exist_ok=True)
        dest = work_dir / file_name
        if src.resolve() == dest.resolve():
            return dest
        shutil.copy2(src, dest)
        return dest
