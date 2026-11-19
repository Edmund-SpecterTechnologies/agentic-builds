"""Vapi `tool-calls` handler: live availability and booking against a GHL calendar.

Contract (docs.vapi.ai/tools/custom-tools): reply HTTP 200 with
    {"results": [{"toolCallId": "...", "result": "<string>"}]}  or  {"toolCallId": "...", "error": "<string>"}
Any other status code is ignored and the assistant hears "no result returned", so failures are reported
in `error`, written as something the assistant can say to the caller.

The caller is on the line, so the tool path does NOT run the full retry ladder: one quick retry, then a
spoken fallback plus an alert to a person.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from .alerts import Alerter
from .config import Settings
from .ghl import GHLClient, GHLError
from .store import Store
from .vapi import call_id_of, caller_number

CALENDAR_DOWN = ("The booking calendar isn't responding. Tell the caller the office will text them "
                 "shortly to confirm a time, and do not promise a specific time.")


class ToolError(Exception):
    """A failure the assistant should hear and handle on the call."""


@dataclass
class ToolContext:
    settings: Settings
    ghl: GHLClient
    store: Store
    alerts: Alerter
    now: Callable[[], datetime]
    message: dict


def _parse_iso(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ToolError(f"'{value}' is not a valid time. Use a start time returned by check_availability.")
    if dt.tzinfo is None:
        raise ToolError("The start time needs a timezone offset. Use a start time from check_availability.")
    return dt


def _spoken(dt: datetime) -> str:
    hour = dt.strftime("%I").lstrip("0")
    minute = "" if dt.minute == 0 else dt.strftime(":%M")
    return f"{dt.strftime('%A, %B')} {dt.day} at {hour}{minute} {dt.strftime('%p')}"


def _window(ctx: ToolContext, date_str: str | None, days: int) -> tuple[int, int]:
    tz = ZoneInfo(ctx.settings.timezone)
    now = ctx.now().astimezone(tz)
    if date_str:
        try:
            start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)
        except ValueError:
            raise ToolError(f"'{date_str}' is not a date. Ask the caller for a day and pass it as YYYY-MM-DD.")
        start = max(start, now)
    else:
        start = now
    end = start + timedelta(days=days)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def check_availability(args: dict, ctx: ToolContext) -> str:
    start_ms, end_ms = _window(ctx, args.get("date"), days=7)
    slots = ctx.ghl.free_slots(start_ms, end_ms, ctx.settings.timezone, attempts=2)
    if not slots:
        return json.dumps({"slots": [], "say": "There are no openings in the next seven days. Offer to take a "
                                                "message so the office can call back."})
    first = slots[0]
    # Offer a real choice: the second option is on a different day when one exists.
    first_day = first[:10]
    second = next((s for s in slots[1:] if s[:10] != first_day), slots[1] if len(slots) > 1 else None)
    offered = [s for s in (first, second) if s]
    say = " or ".join(_spoken(_parse_iso(s)) for s in offered)
    return json.dumps({"slots": offered, "say": f"I have {say}."})


def book_appointment(args: dict, ctx: ToolContext) -> str:
    start = _parse_iso(args.get("start_time", ""))
    if start <= ctx.now():
        raise ToolError("That time has already passed. Call check_availability again.")
    phone = args.get("phone") or caller_number(ctx.message)
    if not phone:
        raise ToolError("I don't have the caller's number. Ask for the best number to text a confirmation to.")
    call_id = call_id_of(ctx.message) or f"phone:{phone}"
    step = f"booking:{start.isoformat()}"

    # Idempotency: models do repeat tool calls. A booking that already landed for this call and time
    # is confirmed again, never created twice.
    previous = ctx.store.get_step(call_id, step)
    if previous and previous["status"] == "done":
        return f"Booked for {_spoken(start)}. Confirmation {previous['result']['appointment_id']}."

    contact_id = ctx.ghl.upsert_contact(phone, args.get("name"), attempts=2)
    if previous and previous["status"] == "sending":
        # The last attempt may have landed (timeout). Look before writing again.
        for event in ctx.ghl.contact_appointments(contact_id):
            if event.get("startTime") and _parse_iso(event["startTime"]) == start:
                ctx.store.set_step(call_id, step, "done", {"appointment_id": event["id"], "contact_id": contact_id})
                return f"Booked for {_spoken(start)}. Confirmation {event['id']}."

    # The slot may have gone since it was offered. Re-check that exact slot before booking.
    day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    open_now = ctx.ghl.free_slots(int(day_start.timestamp() * 1000),
                                  int((day_start + timedelta(days=1)).timestamp() * 1000),
                                  ctx.settings.timezone, attempts=2)
    if not any(_parse_iso(s) == start for s in open_now):
        others = [_spoken(_parse_iso(s)) for s in open_now[:2]]
        alt = f" Offer {' or '.join(others)} instead." if others else " Call check_availability for other days."
        raise ToolError(f"{_spoken(start)} was just taken.{alt}")

    end = start + timedelta(minutes=ctx.settings.appointment_minutes)
    title = f"{args.get('service') or 'Service visit'} - {args.get('name') or phone}"
    ctx.store.set_step(call_id, step, "sending")
    try:
        appointment_id = ctx.ghl.create_appointment(contact_id, start.isoformat(), end.isoformat(), title)
    except GHLError as e:
        if not e.maybe_applied:
            ctx.store.set_step(call_id, step, "failed", error=str(e))
        raise
    ctx.store.set_step(call_id, step, "done", {"appointment_id": appointment_id, "contact_id": contact_id})
    return f"Booked for {_spoken(start)}. Confirmation {appointment_id}."


TOOLS: dict[str, Callable[[dict, ToolContext], str]] = {
    "check_availability": check_availability,
    "book_appointment": book_appointment,
}


def handle_tool_calls(message: dict, settings: Settings, ghl: GHLClient, store: Store, alerts: Alerter,
                      now: Callable[[], datetime] | None = None) -> dict:
    ctx = ToolContext(settings, ghl, store, alerts, now or (lambda: datetime.now(timezone.utc)), message)
    results = []
    for call in message.get("toolCallList") or []:
        tool_call_id = call.get("id", "")
        fn = call.get("function") or {}
        name = fn.get("name", "")
        args = fn.get("arguments") or {}
        try:
            if isinstance(args, str):  # some providers send arguments as a JSON string
                try:
                    args = json.loads(args or "{}")
                except ValueError:
                    raise ToolError("The tool arguments were not valid JSON. Try the call again.")
            handler = TOOLS.get(name)
            if handler is None:
                raise ToolError(f"There is no tool named {name}.")
            results.append({"toolCallId": tool_call_id, "result": handler(args, ctx)})
        except ToolError as e:
            results.append({"toolCallId": tool_call_id, "error": str(e)})
        except GHLError as e:
            alerts.send("error", f"{name} failed on a live call: {e}", call_id_of(message))
            results.append({"toolCallId": tool_call_id, "error": CALENDAR_DOWN})
    return {"results": results}
