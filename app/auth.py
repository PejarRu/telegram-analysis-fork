import os
import asyncio
from typing import Optional

from dotenv import load_dotenv
from telethon import TelegramClient


load_dotenv()


def _get_env_or_raise(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


async def authorize_async(login_code: Optional[str] = None) -> None:
    api_id = int(_get_env_or_raise("TELEGRAM_API_ID"))
    api_hash = _get_env_or_raise("TELEGRAM_API_HASH")
    phone = _get_env_or_raise("TELEGRAM_PHONE")
    username = _get_env_or_raise("TELEGRAM_USERNAME")

    client = TelegramClient(username, api_id, api_hash)
    await client.connect()

    if await client.is_user_authorized():
        print("Telegram session already authorized.")
        await client.disconnect()
        return

    print("Requesting login code from Telegram...")
    await client.send_code_request(phone)

    code = login_code or os.getenv("TELEGRAM_LOGIN_CODE")
    if not code:
        code = input("Introduce el código recibido por Telegram: ")

    await client.sign_in(phone=phone, code=code)
    print("Telegram session authorized successfully.")
    await client.disconnect()


def main() -> None:
    login_code = os.getenv("TELEGRAM_LOGIN_CODE")
    asyncio.run(authorize_async(login_code=login_code))


if __name__ == "__main__":
    main()
