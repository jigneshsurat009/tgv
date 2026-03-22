from __future__ import annotations

import re

from app.models import SourceType

GDRIVE_PAT = re.compile(r"https?://(?:drive|docs)\.google\.com/\S+", re.I)
MEGA_PAT = re.compile(r"https?://(?:www\.)?mega\.(?:nz|io)/\S+", re.I)
SHARED_PAT = re.compile(r"^/shared(?:\s+([A-Za-z0-9_-]+))?$", re.I)
GLINK_PAT = re.compile(r"^/glogin$", re.I)
GCODE_PAT = re.compile(r"^/gauth\s+(.+)$", re.I)


def detect_source(text: str) -> tuple[SourceType, str] | None:
    text = text.strip()
    if GDRIVE_PAT.search(text):
        return SourceType.GDRIVE, GDRIVE_PAT.search(text).group(0)
    if MEGA_PAT.search(text):
        return SourceType.MEGA, MEGA_PAT.search(text).group(0)
    m = SHARED_PAT.match(text)
    if m:
        return SourceType.GDRIVE_SHARED, m.group(1) or "oauth://shared-with-me"
    return None
