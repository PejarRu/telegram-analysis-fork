import json
import asyncio
import requests
import os
import logging
from datetime import datetime
from threading import Lock, Thread
from typing import Optional, Dict

from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import PeerChannel, MessageMediaPhoto, MessageMediaDocument
from telethon import events

logger = logging.getLogger(__name__)

_client_lock = Lock()
_listener_lock = Lock()
_listener_thread: Optional[Thread] = None


# some functions to parse json date
class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        if isinstance(o, bytes):
            return list(o)

        return json.JSONEncoder.default(self, o)

async def _enrich_with_media_download(
    client: TelegramClient,
    message,
    serialized_message: Dict,
    media_dir: str,
    media_base_url: Optional[str],
) -> None:
    """Attach downloadable information for photo/image documents when possible."""
    media = getattr(message, "media", None)
    if not media:
        return

    is_photo = isinstance(media, MessageMediaPhoto)
    is_image_document = isinstance(media, MessageMediaDocument) and getattr(media.document, "mime_type", "").startswith("image/")
    if not (is_photo or is_image_document):
        return

    os.makedirs(media_dir, exist_ok=True)

    try:
        # Telethon appends an appropriate extension when passing a bare path
        target_prefix = os.path.join(media_dir, str(message.id))
        file_path = await client.download_media(media, file=target_prefix)
    except Exception as download_error:
        logger.warning("Unable to download media for message %s: %s", getattr(message, "id", "?"), download_error)
        return

    if not file_path:
        return

    download_info: Dict[str, Optional[str]] = {
        "type": "photo" if is_photo else "document",
        "local_path": file_path,
    }

    if media_base_url:
        relative_path = os.path.relpath(file_path, media_dir)
        public_url = f"{media_base_url.rstrip('/')}/{relative_path.replace(os.sep, '/')}"
        download_info["url"] = public_url

    media_dict = serialized_message.setdefault("media", {})
    media_dict["download_info"] = download_info


async def _post_to_webhook_async(webhook_url: Optional[str], payload: Dict) -> None:
    if not webhook_url:
        return

    loop = asyncio.get_running_loop()

    def _send():
        try:
            response = requests.post(
                webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30,
            )
            logger.info("Sent message to %s, status: %s", webhook_url, response.status_code)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error sending to webhook %s: %s", webhook_url, exc)

    await loop.run_in_executor(None, _send)


async def _store_last_response_async(payload: Dict) -> None:
    loop = asyncio.get_running_loop()

    def _write():
        try:
            os.makedirs('/app/data', exist_ok=True)
            with open('/app/data/last_response.json', 'w') as f:
                json.dump(payload, f)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error writing last response: %s", exc)

    await loop.run_in_executor(None, _write)

async def get_last_messages_async(entity, webhook_url, limit=2):
    # Reading environment variables inside function
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    phone = os.getenv('TELEGRAM_PHONE')
    username = os.getenv('TELEGRAM_USERNAME')

    session_file = os.getenv('TELEGRAM_SESSION_FILE', username)
    session_dir = os.getenv('TELEGRAM_SESSION_DIR', '/app/data')
    media_dir = os.getenv('TELEGRAM_MEDIA_DIR', '/app/data/media')
    media_base_url = os.getenv('MEDIA_BASE_URL')

    if not os.path.isabs(session_file):
        session_path = os.path.join(session_dir, session_file)
    else:
        session_path = session_file

    os.makedirs(os.path.dirname(session_path), exist_ok=True)

    # Create the client and connect
    client = TelegramClient(session_path, api_id, api_hash)

    try:
        await client.connect()

        # Require prior authorization to avoid interactive prompts in docker
        if not await client.is_user_authorized():
            msg = (
                "Telegram client not authorized. Run `python -m app.auth` locally "
                "to complete the login before triggering the service."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        await client.start()
        logger.info("Telegram client started")

        if entity.isdigit():
            entity_obj = PeerChannel(int(entity))
        else:
            entity_obj = entity

        my_channel = await client.get_entity(entity_obj)

        offset_id = 0
        all_messages = []
        total_messages = 0
        total_count_limit = limit

        while True:
            logger.debug(f"Current Offset ID is: {offset_id}, Total Messages: {total_messages}")
            history = await client(GetHistoryRequest(
                peer=my_channel,
                offset_id=offset_id,
                offset_date=None,
                add_offset=0,
                limit=100,
                max_id=0,
                min_id=0,
                hash=0
            ))
            if not history.messages:
                break
            messages = history.messages
            for message in messages:
                if total_count_limit and len(all_messages) >= total_count_limit:
                    break
                serialized_message = json.loads(json.dumps(message.to_dict(), cls=DateTimeEncoder))
                await _enrich_with_media_download(client, message, serialized_message, media_dir, media_base_url)
                all_messages.append(serialized_message)
                # Send to webhook if provided
                if webhook_url:
                    try:
                        os.makedirs('/app/data', exist_ok=True)
                        response = requests.post(
                            webhook_url,
                            json=serialized_message,
                            headers={'Content-Type': 'application/json'}
                        )
                        logger.info(f"Sent message to {webhook_url}, status: {response.status_code}")
                        # Save last response
                        with open('/app/data/last_response.json', 'w') as f:
                            json.dump(serialized_message, f)
                    except Exception as e:
                        logger.error(f"Error sending to webhook: {e}")
            offset_id = messages[len(messages) - 1].id
            total_messages = len(all_messages)
            if total_count_limit != 0 and total_messages >= total_count_limit:
                break

        return all_messages
    finally:
        await client.disconnect()
        logger.info("Telegram client disconnected")


async def listen_for_new_messages_async(entity, webhook_url: Optional[str]) -> None:
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    phone = os.getenv('TELEGRAM_PHONE')
    username = os.getenv('TELEGRAM_USERNAME')

    session_file = os.getenv('TELEGRAM_SESSION_FILE', username)
    session_dir = os.getenv('TELEGRAM_SESSION_DIR', '/app/data')
    media_dir = os.getenv('TELEGRAM_MEDIA_DIR', '/app/data/media')
    media_base_url = os.getenv('MEDIA_BASE_URL')

    if not os.path.isabs(session_file):
        session_path = os.path.join(session_dir, session_file)
    else:
        session_path = session_file

    os.makedirs(os.path.dirname(session_path), exist_ok=True)

    client = TelegramClient(session_path, api_id, api_hash)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            msg = (
                "Telegram client not authorized. Run `python -m app.auth` locally "
                "to complete the login before triggering the service."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        await client.start()
        logger.info("Telegram listener client started")

        if entity.isdigit():
            entity_obj = PeerChannel(int(entity))
        else:
            entity_obj = entity

        target = await client.get_entity(entity_obj)
        logger.info("Listening for new messages on %s", getattr(target, 'title', target))

        async def _handle_event(event):
            message = event.message
            serialized_message = json.loads(json.dumps(message.to_dict(), cls=DateTimeEncoder))
            await _enrich_with_media_download(client, message, serialized_message, media_dir, media_base_url)
            await _post_to_webhook_async(webhook_url, serialized_message)
            await _store_last_response_async(serialized_message)

        client.add_event_handler(_handle_event, events.NewMessage(chats=target))
        await client.run_until_disconnected()
    finally:
        await client.disconnect()
        logger.info("Telegram listener client disconnected")

def get_last_messages(entity, webhook_url, limit=2):
    with _client_lock:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            messages = loop.run_until_complete(get_last_messages_async(entity, webhook_url, limit))
            return messages
        finally:
            loop.close()


def start_listener(entity: str, webhook_url: Optional[str]) -> Optional[Thread]:
    global _listener_thread

    if not entity:
        logger.info("Listener not started: entity is empty")
        return None

    with _listener_lock:
        if _listener_thread and _listener_thread.is_alive():
            logger.info("Listener already running for entity %s", entity)
            return _listener_thread

        def _run_listener():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(listen_for_new_messages_async(entity, webhook_url))
            except Exception as exc:  # noqa: BLE001
                logger.error("Listener stopped due to error: %s", exc)
            finally:
                loop.close()

        thread = Thread(target=_run_listener, name="TelegramListener", daemon=True)
        thread.start()
        _listener_thread = thread
        logger.info("Listener thread started for entity %s", entity)
        return thread
