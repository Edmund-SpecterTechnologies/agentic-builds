"""Live booking on the call. Every assertion about a booking checks the fake GHL's stored
appointments, not the sentence the tool handed back to the assistant."""
import json

from conftest import CALLER


def test_offers_two_slots_on_different_days(h):
    res = h.tool("check_availability", {})
    data = json.loads(res["result"])
    assert data["slots"] == ["2026-11-23T10:00:00-05:00", "2026-11-24T09:00:00-05:00"]
    assert data["say"] == "I have Monday, November 23 at 10 AM or Tuesday, November 24 at 9 AM."


def test_books_into_ghl_using_the_callers_number(h):
    res = h.tool("book_appointment", {"start_time": "2026-11-23T10:00:00-05:00", "name": "Dana Reyes",
                                      "service": "Drain cleaning"})
    assert "Booked for Monday, November 23 at 10 AM" in res["result"]
    [appt] = h.ghl_fake.appointments
    assert appt["startTime"] == "2026-11-23T10:00:00-05:00"
    assert appt["endTime"] == "2026-11-23T11:00:00-05:00"
    assert h.ghl_fake.contacts[appt["contactId"]]["phone"] == CALLER
    assert h.ghl_fake.contacts[appt["contactId"]]["firstName"] == "Dana"


def test_repeated_tool_call_does_not_double_book(h):
    args = {"start_time": "2026-11-23T10:00:00-05:00"}
    first = h.tool("book_appointment", args, tool_call_id="tc_1")
    again = h.tool("book_appointment", args, tool_call_id="tc_2")
    assert len(h.ghl_fake.appointments) == 1
    assert first["result"] == again["result"]


def test_slot_taken_since_it_was_offered_offers_alternatives(h):
    h.ghl_fake.open_slots.remove("2026-11-23T10:00:00-05:00")  # someone else booked it mid-call
    res = h.tool("book_appointment", {"start_time": "2026-11-23T10:00:00-05:00"})
    assert "was just taken" in res["error"] and "11 AM" in res["error"]
    assert h.ghl_fake.appointments == []


def test_timeout_after_the_write_landed_is_resolved_without_a_second_booking(h):
    h.ghl_fake.fail("create_appointment", "timeout_after_write")
    first = h.tool("book_appointment", {"start_time": "2026-11-23T10:00:00-05:00"})
    assert "isn't responding" in first["error"]          # the caller hears the safe fallback
    assert len(h.ghl_fake.appointments) == 1             # ...but GHL did store it
    retry = h.tool("book_appointment", {"start_time": "2026-11-23T10:00:00-05:00"}, tool_call_id="tc_2")
    assert "Booked for" in retry["result"]
    assert len(h.ghl_fake.appointments) == 1, "the retry found the stored booking instead of writing again"


def test_calendar_down_returns_200_with_a_speakable_error_and_alerts(h):
    h.ghl_fake.fail("free_slots", 503, 503)
    res = h.tool("check_availability", {})
    assert "text them shortly" in res["error"]
    assert any("check_availability failed on a live call" in a["message"] for a in h.store.alerts())


def test_bad_arguments_come_back_as_errors_the_model_can_fix(h):
    assert "not a valid time" in h.tool("book_appointment", {"start_time": "Monday at ten"})["error"]
    assert "timezone offset" in h.tool("book_appointment", {"start_time": "2026-11-23T10:00:00"})["error"]
    assert "already passed" in h.tool("book_appointment", {"start_time": "2026-11-20T10:00:00-05:00"})["error"]
    assert "no tool named" in h.tool("cancel_everything", {})["error"]
    assert h.ghl_fake.appointments == []


def test_string_arguments_are_parsed(h):
    res = h.tool("book_appointment", json.dumps({"start_time": "2026-11-24T09:00:00-05:00"}))
    assert "Booked for Tuesday, November 24 at 9 AM" in res["result"]
