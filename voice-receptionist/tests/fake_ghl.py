"""An in-memory GoHighLevel for tests: the endpoints this build calls, response shapes from GHL's API
docs, and fault injection.

Faults are queued per route and consumed in order:
    500 / 429 / 400       return that status without touching state
    "timeout"             raise a read timeout without touching state
    "timeout_after_write" APPLY the write, then raise a timeout: the ambiguous case where the caller
                          cannot tell whether its request landed
    "crash_after_write"   APPLY the write, then raise a non-HTTP error: the worker died mid-step
"""
from __future__ import annotations

import itertools
import json
import re
from datetime import datetime

import httpx

ROUTES = [
    ("GET", re.compile(r"^/calendars/(?P<cal>[^/]+)/free-slots$"), "free_slots"),
    ("POST", re.compile(r"^/calendars/events/appointments$"), "create_appointment"),
    ("POST", re.compile(r"^/contacts/upsert$"), "upsert_contact"),
    ("GET", re.compile(r"^/contacts/(?P<cid>[^/]+)/appointments$"), "contact_appointments"),
    ("GET", re.compile(r"^/contacts/(?P<cid>[^/]+)/notes$"), "list_notes"),
    ("POST", re.compile(r"^/contacts/(?P<cid>[^/]+)/notes$"), "create_note"),
    ("POST", re.compile(r"^/opportunities/upsert$"), "upsert_opportunity"),
    ("POST", re.compile(r"^/conversations/messages$"), "send_sms"),
]


def _instant(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


class FakeGHL:
    def __init__(self, token: str, slots: list[str]):
        self.token = token
        self.open_slots = list(slots)
        self.contacts: dict[str, dict] = {}
        self.appointments: list[dict] = []
        self.notes: list[dict] = []
        self.opportunities: list[dict] = []
        self.sms: list[dict] = []
        self.faults: dict[str, list] = {}
        self.calls: list[tuple[str, str]] = []
        self._ids = itertools.count(1)

    def fail(self, route: str, *actions) -> None:
        self.faults.setdefault(route, []).extend(actions)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    # dispatch ------------------------------------------------------------------------------------
    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != f"Bearer {self.token}" or not request.headers.get("version"):
            return httpx.Response(401, json={"message": "Invalid JWT"})
        path = request.url.path
        for method, pattern, name in ROUTES:
            m = pattern.match(path)
            if m and request.method == method:
                self.calls.append((name, path))
                fault = self.faults.get(name, []).pop(0) if self.faults.get(name) else None
                if isinstance(fault, int):
                    headers = {"Retry-After": "0"} if fault == 429 else {}
                    return httpx.Response(fault, json={"message": "injected"}, headers=headers)
                if fault == "timeout":
                    raise httpx.ReadTimeout("injected", request=request)
                body = json.loads(request.content) if request.content else {}
                status, payload = getattr(self, name)(request, body, **m.groupdict())
                if fault == "timeout_after_write":
                    raise httpx.ReadTimeout("injected after write", request=request)
                if fault == "crash_after_write":  # the worker dies mid-request (deploy, OOM kill)
                    raise RuntimeError("injected crash after write")
                return httpx.Response(status, json=payload)
        return httpx.Response(404, json={"message": f"no route {request.method} {path}"})

    def _id(self, prefix: str) -> str:
        return f"{prefix}{next(self._ids):04d}"

    # endpoints -------------------------------------------------------------------------------------
    def free_slots(self, request, body, cal):
        start = int(request.url.params["startDate"])
        end = int(request.url.params["endDate"])
        out: dict[str, dict] = {}
        for s in self.open_slots:
            ms = int(_instant(s).timestamp() * 1000)
            if start <= ms < end:
                out.setdefault(s[:10], {"slots": []})["slots"].append(s)
        return 200, out

    def create_appointment(self, request, body, **_):
        for field in ("calendarId", "locationId", "contactId", "startTime"):
            if not body.get(field):
                return 422, {"message": f"{field} is required"}
        match = [s for s in self.open_slots if _instant(s) == _instant(body["startTime"])]
        if not match and not body.get("ignoreFreeSlotValidation"):
            return 400, {"message": "The slot you have selected is no longer available"}
        for s in match:
            self.open_slots.remove(s)
        appt = dict(body, id=self._id("appt_"))
        self.appointments.append(appt)
        return 200, appt

    def upsert_contact(self, request, body, **_):
        if not body.get("locationId"):
            return 422, {"message": "locationId is required"}
        for c in self.contacts.values():
            if c.get("phone") and c["phone"] == body.get("phone"):
                c.update({k: v for k, v in body.items() if v})
                return 201, {"new": False, "contact": c}
        c = dict(body, id=self._id("ct_"))
        self.contacts[c["id"]] = c
        return 201, {"new": True, "contact": c}

    def contact_appointments(self, request, body, cid):
        return 200, {"events": [a for a in self.appointments if a["contactId"] == cid]}

    def list_notes(self, request, body, cid):
        return 200, {"notes": [n for n in self.notes if n["contactId"] == cid]}

    def create_note(self, request, body, cid):
        if not body.get("body"):
            return 422, {"message": "body is required"}
        note = {"id": self._id("note_"), "body": body["body"], "contactId": cid}
        self.notes.append(note)
        return 201, {"note": note}

    def upsert_opportunity(self, request, body, **_):
        if not body.get("pipelineId") and not body.get("id"):
            return 422, {"message": "pipelineId is required when id is not sent"}
        for o in self.opportunities:
            if o["contactId"] == body.get("contactId") and o["pipelineId"] == body["pipelineId"]:
                o.update(body)
                return 201, {"new": False, "opportunity": o}
        o = dict(body, id=self._id("opp_"))
        self.opportunities.append(o)
        return 201, {"new": True, "opportunity": o}

    def send_sms(self, request, body, **_):
        if body.get("type") != "SMS" or not body.get("contactId") or not body.get("message"):
            return 422, {"message": "type, contactId and message are required"}
        msg = dict(body, messageId=self._id("msg_"))
        self.sms.append(msg)
        return 201, {"messageId": msg["messageId"], "conversationId": "conv_1"}
