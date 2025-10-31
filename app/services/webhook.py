import asyncio
import json
import logging
import os
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


class WebhookService:
    def __init__(self, base_headers_raw: Optional[str], data_dir: str) -> None:
        self._base_headers_raw = base_headers_raw
        self._data_dir = data_dir
        os.makedirs(self._data_dir, exist_ok=True)

    @staticmethod
    def _parse_headers(raw_value: Optional[str], source_label: str) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if not raw_value:
            return headers

        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = None
        else:
            if isinstance(parsed, dict):
                return {str(key): str(value) for key, value in parsed.items()}
            logger.warning("%s must be a JSON object; got %s", source_label, type(parsed).__name__)
            return headers

        for entry in raw_value.split(','):
            entry = entry.strip()
            if not entry:
                continue
            if ':' not in entry:
                logger.warning("Unable to parse header entry '%s' from %s", entry, source_label)
                continue
            key, value = entry.split(':', 1)
            key = key.strip()
            value = value.strip()
            if key:
                headers[key] = value

        if not headers:
            logger.warning("%s could not be parsed into HTTP headers", source_label)

        return headers

    def build_headers(self, override_raw: Optional[str] = None) -> Dict[str, str]:
        headers: Dict[str, str] = {'Content-Type': 'application/json'}
        headers.update(self._parse_headers(self._base_headers_raw, 'WEBHOOK_HEADERS'))
        if override_raw:
            headers.update(self._parse_headers(override_raw, 'LISTENER_WEBHOOK_HEADERS'))
        return headers

    async def send(self, loop: asyncio.AbstractEventLoop, url: Optional[str], payload: Dict, headers: Dict[str, str]) -> None:
        if not url:
            return

        def _post() -> None:
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                logger.info("Sent message to %s, status: %s", url, response.status_code)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error sending to webhook %s: %s", url, exc)

        await loop.run_in_executor(None, _post)

    async def store_last_response(self, loop: asyncio.AbstractEventLoop, payload: Dict) -> None:
        path = os.path.join(self._data_dir, 'last_response.json')

        def _write() -> None:
            try:
                with open(path, 'w') as handle:
                    json.dump(payload, handle)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error writing last response: %s", exc)

        await loop.run_in_executor(None, _write)
