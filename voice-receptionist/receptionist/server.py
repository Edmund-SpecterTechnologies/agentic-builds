"""The Vapi server URL: one endpoint for every message type.

    tool-calls          answered inline (the caller is waiting)
    end-of-call-report  stored first, acknowledged, then synced to GHL in the background
    status-update       "forwarding" is recorded so the call's outcome is known from stored state
    anything else       acknowledged and ignored

Run:  uvicorn receptionist.server:app --port 8000   (settings come from the environment, see .env.example)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .alerts import Alerter
from .config import Settings
from .ghl import GHLClient
from .store import Store
from .sync import Syncer
from .tools import handle_tool_calls
from .vapi import authorized, call_id_of

log = logging.getLogger("receptionist")


def create_app(settings: Settings, ghl: GHLClient | None = None, store: Store | None = None,
               alerts: Alerter | None = None, now: Callable[[], datetime] | None = None) -> FastAPI:
    if not settings.vapi_secret:
        raise RuntimeError("Refusing to start without a Vapi server secret")
    store = store or Store(settings.db_path)
    ghl = ghl or GHLClient(settings)
    alerts = alerts or Alerter(store, settings.alert_webhook_url)
    syncer = Syncer(settings, ghl, store, alerts)
    clock = now or (lambda: datetime.now(timezone.utc))

    app = FastAPI(title="Voice receptionist backend", docs_url=None, redoc_url=None)
    app.state.store, app.state.syncer = store, syncer

    def sync_in_background(call_id: str) -> None:
        try:
            syncer.process(call_id)
        except Exception as e:  # never lose a call silently: it stays pending for the retry job
            log.exception("sync crashed for %s", call_id)
            alerts.send("error", f"Sync crashed, left for the retry job: {type(e).__name__}: {e}", call_id)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/vapi/webhook")
    async def webhook(request: Request, background: BackgroundTasks):
        if not authorized(request.headers, settings.vapi_secret):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            body = json.loads(await request.body())
        except ValueError:
            return JSONResponse({"error": "body is not JSON"}, status_code=400)
        message = body.get("message") if isinstance(body, dict) else None
        if not isinstance(message, dict):
            return JSONResponse({"error": "missing message object"}, status_code=400)

        kind = message.get("type")
        call_id = call_id_of(message)

        if kind == "tool-calls":
            return await run_in_threadpool(handle_tool_calls, message, settings, ghl, store, alerts, clock)

        if kind == "end-of-call-report":
            if not call_id:
                alerts.send("error", "end-of-call-report arrived with no call id; nothing stored")
                return {"received": False}
            if store.record_event(call_id, message):
                background.add_task(sync_in_background, call_id)
            return {"received": True}

        if kind == "status-update":
            if call_id and message.get("status") == "forwarding":
                # Vapi's docs: "forwarding" means the transfer STARTED, not that anyone answered.
                store.set_step(call_id, "transfer", "started", message.get("destination") or {})
            return {}

        return {"ignored": kind}

    return app


def _app_from_env() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    return create_app(Settings.from_env())


def __getattr__(name: str):  # `uvicorn receptionist.server:app` builds the app only when asked
    if name == "app":
        return _app_from_env()
    raise AttributeError(name)
