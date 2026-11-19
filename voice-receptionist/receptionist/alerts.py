"""Alerts: every alert is stored in the ledger first, then pushed to a webhook if one is set.
A failing alert channel is logged, never raised, so it cannot take the call pipeline down with it."""
from __future__ import annotations

import logging

import httpx

from .store import Store

log = logging.getLogger("receptionist.alerts")


class Alerter:
    def __init__(self, store: Store, webhook_url: str = "", transport: httpx.BaseTransport | None = None):
        self.store = store
        self.webhook_url = webhook_url
        self._transport = transport

    def send(self, level: str, message: str, call_id: str | None = None) -> None:
        text = f"[{level.upper()}] {message}" + (f" (call {call_id})" if call_id else "")
        self.store.add_alert(level, message, call_id)
        log.warning(text)
        if not self.webhook_url:
            return
        try:
            with httpx.Client(timeout=5.0, transport=self._transport) as client:
                client.post(self.webhook_url, json={"text": text}).raise_for_status()
        except httpx.HTTPError as e:
            log.error("alert webhook failed: %s", e)
