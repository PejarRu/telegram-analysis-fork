import configparser
import json
import asyncio
import requests
import os
import logging
from datetime import date, datetime

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.messages import (GetHistoryRequest)
from telethon.tl.types import (
    PeerChannel
)

logger = logging.getLogger(__name__)


# some functions to parse json date
class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        if isinstance(o, bytes):
            return list(o)

        return json.JSONEncoder.default(self, o)


# Reading environment variables
api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')
phone = os.getenv('TELEGRAM_PHONE')
username = os.getenv('TELEGRAM_USERNAME')

# Create the client and connect
client = TelegramClient(username, api_id, api_hash)

async def get_last_messages_async(entity, webhook_url, limit=2):
    await client.start()
    logger.info("Telegram client started")
    # Ensure you're authorized
    if await client.is_user_authorized() == False:
        logger.info("User not authorized, requesting code")
        await client.send_code_request(phone)
        try:
            await client.sign_in(phone, input('Enter the code: '))
        except SessionPasswordNeededError:
            await client.sign_in(password=input('Password: '))

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
            all_messages.append(message.to_dict())
            # Send to webhook
            message_json = json.dumps(message.to_dict(), cls=DateTimeEncoder)
            try:
                response = requests.post(webhook_url, json=message.to_dict(), headers={'Content-Type': 'application/json'})
                logger.info(f"Sent message to {webhook_url}, status: {response.status_code}")
                # Save last response
                with open('/app/data/last_response.json', 'w') as f:
                    json.dump(message.to_dict(), f, cls=DateTimeEncoder)
            except Exception as e:
                logger.error(f"Error sending to webhook: {e}")
        offset_id = messages[len(messages) - 1].id
        total_messages = len(all_messages)
        if total_count_limit != 0 and total_messages >= total_count_limit:
            break

def get_last_messages(entity, webhook_url, limit=2):
    with client:
        client.loop.run_until_complete(get_last_messages_async(entity, webhook_url, limit))
