"""Post-call sync: one end-of-call report becomes four writes in GHL.

    contact        upsert by caller number                 safe to repeat (GHL de-duplicates on phone)
    note           summary, transcript, recording, call id  NOT safe to repeat: GHL notes have no
                                                            idempotency key, so look for this call's
                                                            marker before writing
    opportunity    pipeline stage from the call's outcome   safe to repeat (upsert)
    owner_summary  text to the business owner               at most once: an ambiguous send is never
                                                            repeated automatically; a person checks

The outcome comes from what this system recorded during the call (a booking that landed, a transfer
that started), not from the transcript. What the assistant SAID it did is not evidence that it did it.
"""
from __future__ import annotations

import json
import logging

from .alerts import Alerter
from .config import Settings
from .ghl import GHLClient, GHLError
from .store import Store
from .vapi import CallReport, parse_report

log = logging.getLogger("receptionist.sync")


def marker(call_id: str) -> str:
    return f"[vapi-call:{call_id}]"


def outcome_of(store: Store, call_id: str) -> str:
    if (store.get_step(call_id, "transfer") or {}).get("status") == "started":
        return "emergency"
    return "booked" if store.has_done_step(call_id, "booking:") else "new_lead"


def note_body(report: CallReport, outcome: str) -> str:
    lines = [
        f"AI receptionist call ({outcome.replace('_', ' ')}) {marker(report.call_id)}",
        f"Ended: {report.ended_reason or 'unknown'}",
    ]
    if report.recording_url:
        lines.append(f"Recording: {report.recording_url}")
    if report.summary:
        lines += ["", "Summary:", report.summary]
    if report.transcript:
        lines += ["", "Transcript:", report.transcript]
    return "\n".join(lines)


def owner_text(report: CallReport, outcome: str) -> str:
    head = {"emergency": "EMERGENCY call, transfer started (not confirmed answered)",
            "booked": "New booking", "new_lead": "New call"}[outcome]
    summary = (report.summary or "No summary.").strip()
    if len(summary) > 280:
        summary = summary[:277] + "..."
    return f"{head} from {report.phone}. {summary}"


class Syncer:
    def __init__(self, settings: Settings, ghl: GHLClient, store: Store, alerts: Alerter):
        self.settings, self.ghl, self.store, self.alerts = settings, ghl, store, alerts

    def _step(self, call_id: str, name: str, fn):
        done = self.store.get_step(call_id, name)
        if done and done["status"] == "done":
            return done["result"]
        try:
            result = fn()
        except GHLError as e:
            self.store.set_step(call_id, name, "failed", error=str(e))
            raise
        self.store.set_step(call_id, name, "done", result)
        return result

    def _ensure_note(self, contact_id: str, report: CallReport, outcome: str) -> str:
        tag = marker(report.call_id)
        for note in self.ghl.list_notes(contact_id):
            if tag in (note.get("body") or ""):
                return note["id"]  # an earlier pass wrote it, then timed out before we recorded it
        return self.ghl.create_note(contact_id, note_body(report, outcome))

    def _owner_summary(self, call_id: str, report: CallReport, outcome: str) -> str:
        state = self.store.get_step(call_id, "owner_summary")
        if state and state["status"] == "done":
            return "done"
        if state and state["status"] == "sending":
            return "needs_check"
        self.store.set_step(call_id, "owner_summary", "sending")
        try:
            message_id = self.ghl.send_sms(self.settings.owner_contact_id, owner_text(report, outcome))
        except GHLError as e:
            if e.maybe_applied:
                self.store.set_step(call_id, "owner_summary", "sending", error=str(e))
                return "needs_check"
            self.store.set_step(call_id, "owner_summary", "failed", error=str(e))
            raise
        self.store.set_step(call_id, "owner_summary", "done", {"message_id": message_id})
        return "done"

    def process(self, call_id: str) -> str:
        """Run (or resume) the sync for one call. Returns the event's final status."""
        event = self.store.get_event(call_id)
        if event is None:
            raise KeyError(call_id)
        if event["status"] in ("done", "dead"):
            return event["status"]
        attempt = self.store.start_attempt(call_id)
        report = parse_report(json.loads(event["payload"]))

        if not report.phone:
            self.store.finish_event(call_id, "needs_check", "no caller number on the report")
            self.alerts.send("warning", "Call has no caller number (blocked or web call); not synced to GHL",
                             call_id)
            return "needs_check"

        outcome = outcome_of(self.store, call_id)
        try:
            contact_id = self._step(call_id, "contact", lambda: self.ghl.upsert_contact(report.phone))
            self._step(call_id, "note", lambda: self._ensure_note(contact_id, report, outcome))
            self._step(call_id, "opportunity", lambda: self.ghl.upsert_opportunity(
                contact_id, self.settings.stage_for(outcome), f"AI receptionist - {report.phone}"))
            owner = self._owner_summary(call_id, report, outcome)
        except GHLError as e:
            if attempt >= self.settings.max_sync_attempts or not e.retryable:
                self.store.finish_event(call_id, "dead", str(e))
                self.alerts.send("error", f"Call sync dead-lettered after {attempt} attempt(s): {e}", call_id)
                return "dead"
            self.store.finish_event(call_id, "failed", str(e))
            log.warning("call %s sync attempt %s failed, will retry: %s", call_id, attempt, e)
            return "failed"

        if owner == "needs_check":
            self.store.finish_event(call_id, "needs_check", "owner text may or may not have sent")
            self.alerts.send("warning", "Owner text outcome unknown; check the conversation before resending",
                             call_id)
            return "needs_check"
        self.store.finish_event(call_id, "done")
        return "done"

    def retry_pending(self) -> dict[str, str]:
        """Re-run every event that is pending or failed. Run on a schedule (every few minutes)."""
        return {e["call_id"]: self.process(e["call_id"]) for e in self.store.events("pending", "failed")}
