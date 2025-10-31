import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    phone: str
    username: str
    api_key: str
    session_path: str
    data_dir: str
    media_dir: str
    media_base_url: Optional[str]
    default_webhook: Optional[str]
    listener_entity: Optional[str]
    listener_webhook: Optional[str]
    webhook_headers_raw: Optional[str]
    listener_headers_raw: Optional[str]

    @classmethod
    def from_env(cls) -> "Settings":
        api_id_raw = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        phone = os.getenv("TELEGRAM_PHONE")
        username = os.getenv("TELEGRAM_USERNAME")
        api_key = os.getenv("API_KEY")

        if not all([api_id_raw, api_hash, phone, username, api_key]):
            missing = [
                name
                for name, value in (
                    ("TELEGRAM_API_ID", api_id_raw),
                    ("TELEGRAM_API_HASH", api_hash),
                    ("TELEGRAM_PHONE", phone),
                    ("TELEGRAM_USERNAME", username),
                    ("API_KEY", api_key),
                )
                if not value
            ]
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

        try:
            api_id = int(api_id_raw)
        except ValueError as exc:  # noqa: BLE001
            raise RuntimeError("TELEGRAM_API_ID must be an integer") from exc

        session_dir = os.getenv("TELEGRAM_SESSION_DIR", "/app/data")
        session_file = os.getenv("TELEGRAM_SESSION_FILE", username)
        if os.path.isabs(session_file):
            session_path = session_file
        else:
            session_path = os.path.join(session_dir, session_file)

        data_dir = os.getenv("DATA_DIR", session_dir)
        media_dir = os.getenv("TELEGRAM_MEDIA_DIR", os.path.join(data_dir, "media"))

        return cls(
            api_id=api_id,
            api_hash=api_hash,
            phone=phone,
            username=username,
            api_key=api_key,
            session_path=session_path,
            data_dir=data_dir,
            media_dir=media_dir,
            media_base_url=os.getenv("MEDIA_BASE_URL"),
            default_webhook=os.getenv("N8N_WEBHOOK_URL"),
            listener_entity=os.getenv("TELEGRAM_LISTENER_ENTITY"),
            listener_webhook=os.getenv("LISTENER_WEBHOOK_URL"),
            webhook_headers_raw=os.getenv("WEBHOOK_HEADERS"),
            listener_headers_raw=os.getenv("LISTENER_WEBHOOK_HEADERS"),
        )


settings = Settings.from_env()
