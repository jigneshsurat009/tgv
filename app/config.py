from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    ffmpeg_bin: str = Field(default="ffmpeg", alias="FFMPEG_BIN")
    ffprobe_bin: str = Field(default="ffprobe", alias="FFPROBE_BIN")
    data_dir: Path = Field(default=Path("./data"), alias="DATA_DIR")
    temp_dir: Path = Field(default=Path("./tmp"), alias="TEMP_DIR")
    watermark_text: str = Field(default="@YourChannel", alias="WATERMARK_TEXT")
    watermark_image: str = Field(default="", alias="WATERMARK_IMAGE")
    admin_user_ids: str = Field(default="", alias="ADMIN_USER_IDS")
    google_client_secret_file: Path = Field(default=Path("./secrets/google_client_secret.json"), alias="GOOGLE_CLIENT_SECRET_FILE")
    google_token_dir: Path = Field(default=Path("./data/google_tokens"), alias="GOOGLE_TOKEN_DIR")
    mega_cache_dir: Path = Field(default=Path("./data/mega_cache"), alias="MEGA_CACHE_DIR")

    @property
    def admin_ids(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_user_ids.split(",") if x.strip().isdigit()}

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.google_token_dir.mkdir(parents=True, exist_ok=True)
        self.mega_cache_dir.mkdir(parents=True, exist_ok=True)
        self.google_client_secret_file.parent.mkdir(parents=True, exist_ok=True)
