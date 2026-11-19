# GHL workflows: text-back and reminders

Three workflows per client sub-account. They are plain GHL automation, with no code. This is the
build spec. A workflow is only done when the matching call in [go-live-tests.md](go-live-tests.md)
passes.

**Before any of them can text:** the sub-account's number needs approved A2P 10DLC registration (the
carrier approval for business texting). Start it the day the client's assets arrive. Until it's
approved, texts can be filtered or blocked by carriers even when GHL shows them as sent.

## 1. Missed-call text-back (within 30 seconds)

| | |
|---|---|
| Trigger | **Call Status**, filtered to inbound calls that were not answered (no-answer, busy, voicemail) |
| Step 1 | **If/Else:** contact has DND on for SMS, or tag `opted-out` → end |
| Step 2 | **Send SMS:** "Hi, this is {{business}}. Sorry we missed your call. Reply here or call back anytime; if it's an emergency, call us back and say so." |
| Step 3 | **Add tag** `missed-call-texted` and **Internal notification** to the owner |
| Wait steps | None. Any wait breaks the 30-second promise |

**Agree with the agency first:** which number is the front door. If every call rings straight into
Vapi, calls are rarely "missed" in GHL's sense. In that setup, the case that matters is a caller who
hangs up early. Those calls reach the backend as end-of-call reports with no booking, and they land in
the pipeline as new leads.

## 2. Web-lead text-back (within 30 seconds)

| | |
|---|---|
| Trigger | **Form Submitted** (the client's website form or GHL form), plus **Inbound Webhook** if leads come from elsewhere |
| Step 1 | Same DND / opt-out check |
| Step 2 | **Send SMS:** "Hi {{contact.first_name}}, thanks for reaching out to {{business}}. When's a good time for a quick call? You can also book here: {{calendar link}}" |
| Step 3 | **Create/Update Opportunity** in the client pipeline, stage *New Lead* |

## 3. Appointment reminders (24 h and 1 h)

| | |
|---|---|
| Trigger | **Appointment Status** = confirmed, on the client's calendar |
| Step 1 | **Wait** until 24 hours before the appointment start, then **Send SMS** reminder |
| Step 2 | **Wait** until 1 hour before the appointment start, then **Send SMS** reminder |
| Guard | **If/Else** before each send: appointment still confirmed (not cancelled or rescheduled) |

Bookings made on the call create the appointment with `appointmentStatus: confirmed`, so they enter this
workflow like any other booking. Booked less than 24 hours ahead: confirm in the builder whether GHL
skips a wait whose time has already passed or sends at once, and pick the behavior on purpose.

## Pre-send trace

Before publishing any of these, trace one contact through every step that reads data an earlier step
or another system just wrote, and write down what each read sees at that moment:

- The reminder text reads the appointment time. Does it see the rescheduled time if the caller moved the
  appointment after the trigger fired?
- The opt-out check reads DND. Does a STOP reply set DND before the next scheduled reminder fires?
- The web-lead text reads `first_name`. Is it filled when the form has a single "Name" field?

Anything not traced goes on the go-live checklist as unverified.

## Confirm in the builder

Trigger and filter names above follow GHL's builder at the time of writing; the builder changes. Confirm
the exact Call Status filter values and the wait option's name for "before appointment start" on the
first build, and update this file.
