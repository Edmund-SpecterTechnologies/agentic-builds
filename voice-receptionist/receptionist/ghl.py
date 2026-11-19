"""Thin GoHighLevel API v2 client with the retry rules this build depends on.

Retry rules:
  * 429 and 5xx responses, timeouts, and connection errors are retried with backoff (Retry-After
    is honoured on 429).
  * Other 4xx responses are never retried: the request is wrong, and repeating it changes nothing.
  * Writes that GHL cannot de-duplicate (notes, appointments, SMS) are sent ONCE per pass
    (`attempts=1`). The caller decides whether a repeat is safe, because a timeout does not mean
    the write failed: GHL's own docs say retrying a timed-out note request "can create a second note".
"""
from __future__ import annotations

import time
from typing import Callable

import httpx

from .config import Settings


class GHLError(Exception):
    def __init__(self, message: str, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable

    @property
    def maybe_applied(self) -> bool:
        """True when the write may have landed even though we got an error (timeout, 5xx)."""
        return self.status is None or self.status >= 500


class GHLClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None,
                 attempts: int = 3, timeout: float = 10.0, sleep: Callable[[float], None] = time.sleep):
        self.settings = settings
        self.attempts = attempts
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=settings.ghl_base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {settings.ghl_token}",
                "Version": settings.ghl_version,
                "Accept": "application/json",
            },
        )

    # transport ---------------------------------------------------------------------------------
    @staticmethod
    def _delay(attempt: int, retry_after: str | None = None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), 30.0)
            except ValueError:
                pass
        return min(0.5 * 2 ** (attempt - 1), 8.0)

    def request(self, method: str, path: str, *, json: dict | None = None, params: dict | None = None,
                attempts: int | None = None) -> dict:
        tries = attempts or self.attempts
        for attempt in range(1, tries + 1):
            retry_after = None
            try:
                r = self._http.request(method, path, json=json, params=params)
            except httpx.TimeoutException:
                err = GHLError(f"{method} {path}: timed out", retryable=True)
            except httpx.TransportError as e:
                err = GHLError(f"{method} {path}: {type(e).__name__}", retryable=True)
            else:
                if r.status_code < 300:
                    return r.json() if r.content else {}
                retryable = r.status_code == 429 or r.status_code >= 500
                err = GHLError(f"{method} {path}: HTTP {r.status_code} {r.text[:200]}",
                               status=r.status_code, retryable=retryable)
                retry_after = r.headers.get("Retry-After")
            if not err.retryable or attempt == tries:
                raise err
            self._sleep(self._delay(attempt, retry_after))
        raise AssertionError("unreachable")

    # endpoints -----------------------------------------------------------------------------------
    def free_slots(self, start_ms: int, end_ms: int, timezone: str, attempts: int | None = None) -> list[str]:
        """All open slot start times (ISO 8601 with offset) in [start_ms, end_ms), sorted."""
        data = self.request("GET", f"/calendars/{self.settings.ghl_calendar_id}/free-slots",
                            params={"startDate": start_ms, "endDate": end_ms, "timezone": timezone},
                            attempts=attempts)
        slots: list[str] = []
        for day, value in data.items():
            if isinstance(value, dict) and isinstance(value.get("slots"), list):
                slots.extend(value["slots"])
        return sorted(slots)

    def upsert_contact(self, phone: str, name: str | None = None, attempts: int | None = None) -> str:
        body = {"locationId": self.settings.ghl_location_id, "phone": phone, "source": "AI receptionist"}
        if name:
            first, _, last = name.strip().partition(" ")
            body["firstName"] = first
            if last:
                body["lastName"] = last
        return self.request("POST", "/contacts/upsert", json=body, attempts=attempts)["contact"]["id"]

    def contact_appointments(self, contact_id: str) -> list[dict]:
        return self.request("GET", f"/contacts/{contact_id}/appointments").get("events", [])

    def create_appointment(self, contact_id: str, start_iso: str, end_iso: str, title: str) -> str:
        body = {
            "calendarId": self.settings.ghl_calendar_id,
            "locationId": self.settings.ghl_location_id,
            "contactId": contact_id,
            "startTime": start_iso,
            "endTime": end_iso,
            "title": title,
            "appointmentStatus": "confirmed",
        }
        return self.request("POST", "/calendars/events/appointments", json=body, attempts=1)["id"]

    def list_notes(self, contact_id: str) -> list[dict]:
        return self.request("GET", f"/contacts/{contact_id}/notes").get("notes", [])

    def create_note(self, contact_id: str, body: str) -> str:
        return self.request("POST", f"/contacts/{contact_id}/notes", json={"body": body}, attempts=1)["note"]["id"]

    def upsert_opportunity(self, contact_id: str, stage_id: str, name: str) -> str:
        body = {
            "locationId": self.settings.ghl_location_id,
            "pipelineId": self.settings.ghl_pipeline_id,
            "pipelineStageId": stage_id,
            "contactId": contact_id,
            "name": name,
            "status": "open",
        }
        return self.request("POST", "/opportunities/upsert", json=body)["opportunity"]["id"]

    def send_sms(self, contact_id: str, message: str) -> str:
        data = self.request("POST", "/conversations/messages",
                            json={"type": "SMS", "contactId": contact_id, "message": message}, attempts=1)
        return data.get("messageId") or data.get("id") or ""
