import json
import asyncio
import requests
import os
"""Deprecated module.

The Telegram integration lives in :mod:`app.services.telegram`.  This stub is
kept only for backwards compatibility and will be removed in a future release.
"""

from .services.telegram import TelegramService  # noqa: F401

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

        loop = asyncio.get_running_loop()
        with _listener_lock:
            _listener_state["loop"] = loop
            _listener_state["client"] = client

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
            await _post_to_webhook_async(webhook_url, serialized_message, headers=headers)
            await _store_last_response_async(serialized_message)

        client.add_event_handler(_handle_event, events.NewMessage(chats=target))
        await client.run_until_disconnected()
    finally:
        with _listener_lock:
            if _listener_state.get("client") is client:
                _listener_state.update({"loop": None, "client": None})
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


def get_message_by_id(entity, message_id, webhook_url=None):
    with _listener_lock:
        listener_client = _listener_state.get("client")
        listener_loop = _listener_state.get("loop")

    if listener_client and listener_loop:
        try:
            future = asyncio.run_coroutine_threadsafe(
                _retrieve_message_with_client(listener_client, entity, message_id, webhook_url),
                listener_loop,
            )
            return future.result()
        except Exception as exc:  # noqa: BLE001
            logger.error("Listener client retrieval failed: %s", exc, exc_info=True)

    with _client_lock:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            message = loop.run_until_complete(get_message_by_id_async(entity, message_id, webhook_url))
            return message
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
