import asyncio
import json
import logging
import os
from datetime import datetime
from threading import Thread
from typing import Dict, List, Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, PeerChannel

from app.config import Settings
from .webhook import WebhookService

logger = logging.getLogger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):  # noqa: D401 - inherited docstring not needed
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return list(obj)
        return super().default(obj)


class TelegramService:
    def __init__(self, settings: Settings, webhook_service: WebhookService) -> None:
        self._settings = settings
        self._webhook_service = webhook_service

        self._loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._run_loop, name="TelegramServiceLoop", daemon=True)
        self._thread.start()

        self._media_serializer = URLSafeTimedSerializer(
            self._settings.media_signing_secret,
            salt="telegram-analysis-media",
        )

        init_future = asyncio.run_coroutine_threadsafe(self._initialise(), self._loop)
        init_future.result()

        if self._settings.listener_entity:
            listener_future = asyncio.run_coroutine_threadsafe(self._start_listener(), self._loop)
            try:
                listener_future.result()
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to start listener: %s", exc)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _initialise(self) -> None:
        self._client_lock = asyncio.Lock()  # type: ignore[attr-defined]

        # NUEVO: Verificar que existen archivos/directorios esenciales
        missing_items = []

        # Verificar que el directorio de sesión existe y es escribible
        session_dir = os.path.dirname(self._settings.session_path)
        if not os.path.exists(session_dir):
            missing_items.append(f"Session directory: {session_dir}")
        elif not os.access(session_dir, os.W_OK):
            missing_items.append(f"Session directory not writable: {session_dir}")

        # Verificar directorio de media
        if not os.path.exists(self._settings.media_dir):
            missing_items.append(f"Media directory: {self._settings.media_dir}")
        elif not os.access(self._settings.media_dir, os.W_OK):
            missing_items.append(f"Media directory not writable: {self._settings.media_dir}")

        # Si hay elementos faltantes, mostrar error claro
        if missing_items:
            error_msg = (
                "⚠ DEPLOYMENT ERROR: Missing essential files/directories:\n\n"
                + "\n".join(f"  - {item}" for item in missing_items)
                + "\n\nAction required:\n"
                + "  1. Mount persistent volume: -v utils-telegram-data:/app/data\n"
                + "  2. Ensure session file exists in mounted volume\n"
                + "  3. Check file permissions (user: appuser, UID: 1000)\n"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        os.makedirs(session_dir, exist_ok=True)
        os.makedirs(self._settings.media_dir, exist_ok=True)

        self._client = TelegramClient(
            self._settings.session_path,
            self._settings.api_id,
            self._settings.api_hash,
        )

        await self._client.connect()
        if not await self._client.is_user_authorized():
            msg = (
                "Telegram client not authorized. Run `python -m app.auth` locally "
                "to complete the login before triggering the service."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        await self._client.start()
        logger.info("Telegram client started")

        self._base_webhook_headers = self._webhook_service.build_headers()
        self._listener_headers = self._webhook_service.build_headers(self._settings.listener_headers_raw)
        self._listener_webhook = self._settings.listener_webhook or self._settings.default_webhook

    async def _resolve_entity(self, entity: str):
        if entity.isdigit():
            entity_obj = PeerChannel(int(entity))
        else:
            entity_obj = entity
        return await self._client.get_entity(entity_obj)

    async def _enrich_with_media(self, message, serialized: Dict, entity: Optional[str] = None) -> None:
        media = getattr(message, "media", None)
        if not media:
            return

        is_photo = isinstance(media, MessageMediaPhoto)
        is_image_document = isinstance(media, MessageMediaDocument) and getattr(media.document, "mime_type", "").startswith("image/")
        if not (is_photo or is_image_document):
            return

        os.makedirs(self._settings.media_dir, exist_ok=True)

        try:
            target_prefix = os.path.join(self._settings.media_dir, str(message.id))
            file_path = await self._client.download_media(media, file=target_prefix)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unable to download media for message %s: %s", getattr(message, "id", "?"), exc)
            return

        if not file_path:
            return

        download_info: Dict[str, Optional[str]] = {
            "type": "photo" if is_photo else "document",
            "local_path": file_path,
        }

        relative_path = os.path.relpath(file_path, self._settings.media_dir)
        download_info["relative_path"] = relative_path

        signed_url = self._build_signed_media_url(relative_path, entity=entity, message_id=getattr(message, "id", None))
        if signed_url:
            download_info["signed_url"] = signed_url

        if self._settings.media_base_url:
            public_url = f"{self._settings.media_base_url.rstrip('/')}/{relative_path.replace(os.sep, '/')}"
            download_info["url"] = public_url

        media_dict = serialized.setdefault("media", {})
        media_dict["download_info"] = download_info

    async def _serialise_message(self, message, entity: Optional[str] = None) -> Dict:
        payload = json.loads(json.dumps(message.to_dict(), cls=DateTimeEncoder))
        await self._enrich_with_media(message, payload, entity)
        return payload

    def _build_signed_media_url(
        self,
        relative_path: str,
        entity: Optional[str] = None,
        message_id: Optional[int] = None,
    ) -> Optional[str]:
        if not relative_path:
            return None
        payload: Dict[str, object] = {"path": relative_path}
        if entity:
            payload["entity"] = entity
        if message_id is not None:
            payload["message_id"] = int(message_id)
        token = self._media_serializer.dumps(payload)
        return f"/media/{token}"

    async def _redownload_media(self, entity: str, message_id: int, absolute_path: str) -> Optional[str]:
        async with self._client_lock:
            target = await self._resolve_entity(entity)
            message = await self._client.get_messages(target, ids=int(message_id))
            if isinstance(message, list):
                message = message[0] if message else None
            if not message or not getattr(message, "media", None):
                return None
            try:
                downloaded = await self._client.download_media(message.media, file=absolute_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Unable to redownload media for %s/%s: %s", entity, message_id, exc)
                return None
            return downloaded

    def get_media_path_from_token(
        self,
        token: str,
        entity_override: Optional[str] = None,
        message_id_override: Optional[int] = None,
    ) -> str:
        try:
            data = self._media_serializer.loads(token, max_age=self._settings.media_url_ttl)
        except SignatureExpired:
            logger.warning("Signed media link expired; serving anyway for token: %s", token)
            data = self._media_serializer.loads(token)
        relative_path = data.get("path")
        if not relative_path:
            raise BadSignature("Missing path")

        normalized = os.path.normpath(relative_path)
        if normalized.startswith(".."):
            raise BadSignature("Invalid path")

        media_root = os.path.abspath(self._settings.media_dir)
        absolute_path = os.path.abspath(os.path.join(media_root, normalized))
        if not absolute_path.startswith(media_root):
            raise BadSignature("Traversal detected")
        if not os.path.exists(absolute_path):
            entity = data.get("entity") or entity_override
            message_id = data.get("message_id") or message_id_override
            if entity and message_id:
                os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self._redownload_media(str(entity), int(message_id), absolute_path),
                        self._loop,
                    )
                    future.result(timeout=30)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to redownload missing media: %s", exc)
        return absolute_path

    async def _dispatch_webhook(self, payload: Dict, webhook_url: Optional[str], headers: Dict[str, str]) -> None:
        if not webhook_url:
            return
        await self._webhook_service.send(self._loop, webhook_url, payload, headers)
        await self._webhook_service.store_last_response(self._loop, payload)

    async def _fetch_history(self, entity: str, limit: int, webhook_url: Optional[str]) -> List[Dict]:
        if limit <= 0:
            return []

        webhook_headers = self._base_webhook_headers
        effective_webhook = webhook_url or self._settings.default_webhook
        async with self._client_lock:
            target = await self._resolve_entity(entity)

            offset_id = 0
            all_serialised: List[Dict] = []

            while len(all_serialised) < limit:
                history = await self._client(GetHistoryRequest(
                    peer=target,
                    offset_id=offset_id,
                    offset_date=None,
                    add_offset=0,
                    limit=min(100, limit - len(all_serialised)),
                    max_id=0,
                    min_id=0,
                    hash=0,
                ))

                if not history.messages:
                    break

                for message in history.messages:
                    serialised = await self._serialise_message(message, entity)
                    serialised["source_entity"] = entity
                    all_serialised.append(serialised)
                    if effective_webhook:
                        await self._dispatch_webhook(serialised, effective_webhook, webhook_headers)

                    if len(all_serialised) >= limit:
                        break

                offset_id = history.messages[-1].id

        return all_serialised

    async def _fetch_single(self, entity: str, message_id: int, webhook_url: Optional[str]) -> Optional[Dict]:
        webhook_headers = self._base_webhook_headers
        effective_webhook = webhook_url or self._settings.default_webhook

        async with self._client_lock:
            target = await self._resolve_entity(entity)
            message = await self._client.get_messages(target, ids=int(message_id))

            if isinstance(message, list):
                message = message[0] if message else None

            if not message:
                return None

            serialised = await self._serialise_message(message, entity)
            serialised["source_entity"] = entity
            if effective_webhook:
                await self._dispatch_webhook(serialised, effective_webhook, webhook_headers)
            return serialised

    async def _start_listener(self) -> None:
        if not self._listener_webhook:
            logger.info("Listener configured but webhook missing; skipping real-time forwarding")
            return

        target = await self._resolve_entity(self._settings.listener_entity)  # type: ignore[arg-type]
        headers = self._listener_headers
        webhook_url = self._listener_webhook

        @self._client.on(events.NewMessage(chats=target))
        async def handler(event):  # noqa: ANN001 - Telethon provides event
            async with self._client_lock:
                serialised = await self._serialise_message(event.message, self._settings.listener_entity)
                await self._dispatch_webhook(serialised, webhook_url, headers)

        title = getattr(target, "title", str(target))
        logger.info("Listening for new messages on %s", title)

    def get_last_messages(self, entity: str, limit: int, webhook_url: Optional[str]) -> List[Dict]:
        future = asyncio.run_coroutine_threadsafe(
            self._fetch_history(entity, limit, webhook_url),
            self._loop,
        )
        return future.result()

    def get_message_by_id(self, entity: str, message_id: int, webhook_url: Optional[str]) -> Optional[Dict]:
        future = asyncio.run_coroutine_threadsafe(
            self._fetch_single(entity, message_id, webhook_url),
            self._loop,
        )
        return future.result()
