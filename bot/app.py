from __future__ import annotations

import logging

from fastapi import FastAPI, Header, HTTPException, Request

from .ai import AIQueryAnalyzer
from .config import Settings
from .max_api import MaxAPI
from .service import SYSTEMS, handle_update
from .storage import Storage

logging.basicConfig(level=logging.INFO)
settings = Settings.from_env()
storage = Storage(settings.database_path)
api = MaxAPI(settings.token, settings.api_base)
ai = AIQueryAnalyzer(
    settings.ai_api_key,
    settings.ai_base_url,
    settings.ai_model,
    {key: value["name"] for key, value in SYSTEMS.items()},
)
app = FastAPI(title="YANAO MAX Search Bot")


@app.get("/health")
async def health():
    counts = storage.counts()
    ready = all(counts.get(source) for source in ("rsed", "esku", "kb", "files"))
    return {"status": "ok" if ready else "index_empty", "pages": counts}


@app.post("/webhook")
async def webhook(request: Request, x_max_bot_api_secret: str | None = Header(default=None)):
    if settings.webhook_secret and x_max_bot_api_secret != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    update = await request.json()
    await handle_update(update, storage, api, ai)
    return {"ok": True}


@app.on_event("shutdown")
async def shutdown():
    await api.close()
    await ai.close()
