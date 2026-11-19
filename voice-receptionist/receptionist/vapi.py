"""Reading Vapi server messages.

Documented shape (docs.vapi.ai/server-url/events): every POST body is {"message": {"type": ..., "call": {...}}}.
For an end-of-call report the docs show `endedReason`, `call`, and `artifact` with `transcript`, `messages`,
and a `recording` object. Fields the events page does not spell out (caller number, summary, recording URL
keys) are read defensively from every place they are known to appear, and a missing caller number is
treated as a case for a person, never guessed.
"""
from __future__ import annotations

import hmac
from dataclasses import dataclass


def authorized(headers, secret: str) -> bool:
    """Vapi sends the shared secret as `Authorization: Bearer <token>` (default credential) or in
    `X-Vapi-Secret` (legacy). Constant-time comparison either way."""
    if not secret:
        return False
    candidates = [headers.get("x-vapi-secret", "")]
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        candidates.append(auth[7:].strip())
    return any(c and hmac.compare_digest(c.encode(), secret.encode()) for c in candidates)


@dataclass
class CallReport:
    call_id: str
    phone: str | None
    transcript: str
    summary: str
    recording_url: str | None
    ended_reason: str
    started_at: str | None
    ended_at: str | None


def call_id_of(message: dict) -> str | None:
    call = message.get("call") or {}
    return call.get("id") or None


def caller_number(message: dict) -> str | None:
    for source in (message.get("customer"), (message.get("call") or {}).get("customer")):
        if isinstance(source, dict) and source.get("number"):
            return source["number"]
    return None


def parse_report(message: dict) -> CallReport:
    call = message.get("call") or {}
    artifact = message.get("artifact") or {}
    recording = artifact.get("recording") or {}
    mono = recording.get("mono") or {}
    analysis = message.get("analysis") or call.get("analysis") or {}
    return CallReport(
        call_id=call.get("id", ""),
        phone=caller_number(message),
        transcript=artifact.get("transcript") or message.get("transcript") or "",
        summary=analysis.get("summary") or message.get("summary") or "",
        recording_url=(recording.get("stereoUrl") or mono.get("combinedUrl") or recording.get("url")
                       or artifact.get("recordingUrl") or message.get("recordingUrl")),
        ended_reason=message.get("endedReason") or call.get("endedReason") or "",
        started_at=message.get("startedAt") or call.get("startedAt"),
        ended_at=message.get("endedAt") or call.get("endedAt"),
    )
