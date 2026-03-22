from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


class GoogleAuthError(RuntimeError):
    pass


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class GoogleDriveOAuth:
    def __init__(self, client_secret_path: Path, token_root: Path):
        self.client_secret_path = client_secret_path
        self.token_root = token_root
        self.token_root.mkdir(parents=True, exist_ok=True)

    def _token_file(self, user_id: int) -> Path:
        return self.token_root / f"google_token_{user_id}.json"

    def has_client_secret(self) -> bool:
        return self.client_secret_path.exists() and self.client_secret_path.is_file()

    def _save_credentials(self, user_id: int, creds: Credentials) -> None:
        self._token_file(user_id).write_text(creds.to_json(), encoding="utf-8")

    def load_credentials(self, user_id: int) -> Credentials | None:
        token_file = self._token_file(user_id)
        if not token_file.exists():
            return None
        data = json.loads(token_file.read_text(encoding="utf-8"))
        creds = Credentials.from_authorized_user_info(data, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save_credentials(user_id, creds)
        return creds

    def start_auth(self, user_id: int) -> tuple[str, str]:
        if not self.has_client_secret():
            raise GoogleAuthError(
                f"Missing Google OAuth client secrets file at {self.client_secret_path}. "
                "Add a Desktop OAuth client JSON and try again."
            )
        flow = Flow.from_client_secrets_file(str(self.client_secret_path), scopes=SCOPES)
        flow.redirect_uri = "http://localhost"
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        state_file = self.token_root / f"google_state_{user_id}.txt"
        state_file.write_text(state, encoding="utf-8")
        return auth_url, state

    def finish_auth_from_redirect(self, user_id: int, redirect_url: str) -> None:
        if not self.has_client_secret():
            raise GoogleAuthError(
                f"Missing Google OAuth client secrets file at {self.client_secret_path}."
            )
        state_file = self.token_root / f"google_state_{user_id}.txt"
        if not state_file.exists():
            raise GoogleAuthError("OAuth session was not started. Use /glogin first.")
        state = state_file.read_text(encoding="utf-8").strip()
        flow = Flow.from_client_secrets_file(str(self.client_secret_path), scopes=SCOPES, state=state)
        flow.redirect_uri = "http://localhost"
        flow.fetch_token(authorization_response=redirect_url)
        self._save_credentials(user_id, flow.credentials)
        try:
            state_file.unlink()
        except FileNotFoundError:
            pass

    @staticmethod
    def looks_like_redirect_url(text: str) -> bool:
        parsed = urlparse(text.strip())
        if parsed.scheme not in {"http", "https"}:
            return False
        query = parse_qs(parsed.query)
        return "code" in query and "state" in query

    def drive_service(self, user_id: int):
        creds = self.load_credentials(user_id)
        if not creds:
            raise GoogleAuthError("Google account is not linked yet. Use /glogin first.")
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def list_shared_items(self, user_id: int, folder_id: str | None = None) -> list[dict[str, Any]]:
        service = self.drive_service(user_id)
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        fields = "nextPageToken, files(id, name, mimeType, size, webViewLink, parents)"
        if folder_id:
            query = f"'{folder_id}' in parents and trashed=false"
        else:
            query = "sharedWithMe=true and trashed=false"
        while True:
            response = (
                service.files()
                .list(
                    q=query,
                    fields=fields,
                    pageSize=200,
                    pageToken=page_token,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )
            items.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return items

    def download_file(self, user_id: int, file_id: str, dest_path: Path) -> Path:
        service = self.drive_service(user_id)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        with dest_path.open("wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return dest_path
