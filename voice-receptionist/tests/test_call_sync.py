"""Post-call sync to GHL: duplicates, partial failures, ambiguous writes, and dead letters.
Assertions read the fake GHL's stored contacts, notes, opportunities, and texts."""
from conftest import CALLER


def test_happy_path_writes_contact_note_stage_and_owner_text(h):
    h.tool("book_appointment", {"start_time": "2026-11-23T10:00:00-05:00"})
    assert h.report().json() == {"received": True}
    assert h.store.get_event("call_demo_0001")["status"] == "done"

    [contact] = [c for c in h.ghl_fake.contacts.values() if c["phone"] == CALLER]
    [note] = h.ghl_fake.notes
    assert note["contactId"] == contact["id"]
    assert "[vapi-call:call_demo_0001]" in note["body"]
    assert "call_demo_0001-stereo.wav" in note["body"] and "slow kitchen drain" in note["body"]
    [opp] = h.ghl_fake.opportunities
    assert opp["pipelineStageId"] == "stage_booked", "outcome comes from the stored booking"
    [sms] = h.ghl_fake.sms
    assert sms["contactId"] == "ct_owner" and sms["message"].startswith("New booking from +17275550142")


def test_same_report_delivered_twice_writes_once(h):
    h.report()
    h.report()
    h.syncer.retry_pending()
    assert len(h.ghl_fake.notes) == 1 and len(h.ghl_fake.sms) == 1 and len(h.ghl_fake.opportunities) == 1


def test_no_booking_and_no_transfer_is_a_new_lead(h):
    h.report()
    assert h.ghl_fake.opportunities[0]["pipelineStageId"] == "stage_new"


def test_transfer_started_marks_emergency_and_says_unconfirmed(h):
    h.post({"message": {"type": "status-update", "status": "forwarding", "call": {"id": "call_demo_0001"},
                        "destination": {"type": "number", "number": "+17275550199"}}})
    h.report()
    assert h.ghl_fake.opportunities[0]["pipelineStageId"] == "stage_emergency"
    assert "transfer started (not confirmed answered)" in h.ghl_fake.sms[0]["message"]


def test_rate_limit_is_retried_inside_the_pass(h):
    h.ghl_fake.fail("upsert_contact", 429, 429)
    h.report()
    assert h.store.get_event("call_demo_0001")["status"] == "done"


def test_partial_failure_resumes_without_repeating_finished_steps(h):
    h.ghl_fake.fail("upsert_opportunity", 503, 503, 503)   # outlasts the in-pass retries
    h.report()
    assert h.store.get_event("call_demo_0001")["status"] == "failed"
    assert len(h.ghl_fake.notes) == 1 and h.ghl_fake.sms == []

    assert h.syncer.retry_pending() == {"call_demo_0001": "done"}
    assert len(h.ghl_fake.notes) == 1, "the note step was done and must not be written again"
    assert len(h.ghl_fake.opportunities) == 1 and len(h.ghl_fake.sms) == 1


def test_note_that_landed_before_a_timeout_is_found_not_duplicated(h):
    h.ghl_fake.fail("create_note", "timeout_after_write")
    h.report()
    assert h.store.get_event("call_demo_0001")["status"] == "failed"
    assert len(h.ghl_fake.notes) == 1                     # GHL stored it despite the timeout
    h.syncer.retry_pending()
    assert len(h.ghl_fake.notes) == 1, "the retry found this call's marker instead of writing again"
    assert h.store.get_event("call_demo_0001")["status"] == "done"


def test_owner_text_with_unknown_outcome_is_never_resent_automatically(h):
    h.ghl_fake.fail("send_sms", "timeout_after_write")
    h.report()
    assert h.store.get_event("call_demo_0001")["status"] == "needs_check"
    h.syncer.retry_pending()
    assert len(h.ghl_fake.sms) == 1, "an owner who got the text once must not get it twice"
    assert any("Owner text outcome unknown" in a["message"] for a in h.store.alerts())


def test_bad_request_is_dead_lettered_at_once_with_an_alert(h):
    h.ghl_fake.fail("upsert_opportunity", 422)
    h.report()
    assert h.store.get_event("call_demo_0001")["status"] == "dead"
    assert any("dead-lettered" in a["message"] for a in h.store.alerts())


def test_persistent_outage_is_dead_lettered_after_max_attempts(h):
    h.ghl_fake.fail("upsert_contact", *([500] * 30))
    h.report()
    h.syncer.retry_pending()
    assert h.store.get_event("call_demo_0001")["status"] == "failed"
    h.syncer.retry_pending()
    event = h.store.get_event("call_demo_0001")
    assert event["status"] == "dead" and event["attempts"] == h.settings.max_sync_attempts


def test_call_with_no_caller_number_goes_to_a_person(h):
    h.report(customer=None, call={"id": "call_demo_0001"})
    assert h.store.get_event("call_demo_0001")["status"] == "needs_check"
    assert h.ghl_fake.contacts == {}


def test_worker_crash_mid_owner_text_is_not_resent_by_the_retry_job(h):
    h.ghl_fake.fail("send_sms", "crash_after_write")
    h.report()
    assert h.store.get_event("call_demo_0001")["status"] == "pending"   # left for the retry job
    assert any("Sync crashed" in a["message"] for a in h.store.alerts())
    assert h.syncer.retry_pending() == {"call_demo_0001": "needs_check"}
    assert len(h.ghl_fake.sms) == 1, "the text may have gone out before the crash, so it is never resent"
