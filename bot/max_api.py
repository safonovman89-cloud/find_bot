from __future__ import annotations

import ssl

import httpx


class MaxAPI:
    def __init__(self, token: str, base_url: str):
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": token, "Content-Type": "application/json"},
            verify=ssl.create_default_context(),
            timeout=30,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def send(self, target_type: str, target_id: int, text: str, buttons=None) -> None:
        body: dict = {"text": text}
        if buttons:
            body["attachments"] = [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]
        response = await self.client.post("/messages", params={target_type: target_id}, json=body)
        response.raise_for_status()

    async def answer_callback(self, callback_id: str) -> None:
        response = await self.client.post("/answers", params={"callback_id": callback_id}, json={})
        response.raise_for_status()

    async def subscribe(self, url: str, secret: str) -> dict:
        body = {"url": url, "update_types": ["bot_started", "message_created", "message_callback"]}
        if secret:
            body["secret"] = secret
        response = await self.client.post("/subscriptions", json=body)
        response.raise_for_status()
        return response.json()

    async def updates(self, marker: int | None = None, timeout: int = 30) -> dict:
        params: dict[str, str | int] = {
            "timeout": timeout,
            "limit": 100,
            "types": "bot_started,message_created,message_callback",
        }
        if marker is not None:
            params["marker"] = marker
        response = await self.client.get("/updates", params=params)
        response.raise_for_status()
        return response.json()
