# Go-live tests

Scripted calls made to the client's real number before launch. A test passes on what GHL and the
ledger stored, never on what the assistant said. "You're all booked" is the assistant's claim. The
appointment in the GHL calendar is the evidence.

Record for each: date, who called, the Vapi call id, and the result. A test that can't be checked on
stored state is marked **unverified**, not passed.

| # | Script | Pass when |
|---|---|---|
| 1 | Non-urgent booking: "My kitchen drain is slow." Accept the first time offered. | GHL calendar has the appointment at the offered time; contact has the caller's number and a note with summary, transcript, and recording link; opportunity is in *Booked*; owner got the text. |
| 2 | Emergency: "There's water coming through the ceiling." | Call transfers to the on-call number, **and the on-call person confirms the phone rang and they answered**; opportunity is in *Emergency*. A `forwarding` status alone is not a pass. |
| 3 | Gas smell. | Assistant tells the caller to leave and says "nine one one" correctly, then transfers. Listen to the recording. |
| 4 | Ask for a day with no openings. | Assistant offers other days and does not invent a time; no appointment is created. |
| 5 | Pick a time, then have someone book that slot in GHL before you confirm. | Assistant says it was taken and offers alternatives; exactly one appointment in that slot. |
| 6 | Hang up after the greeting. | The report reaches the ledger; contact plus a *New Lead* opportunity in GHL. |
| 7 | Call from a blocked number. | Event is `needs_check` and an alert fired; no junk contact in GHL. |
| 8 | Call the front-door number and let it ring out (if the setup has one). | Text-back arrives within 30 seconds. Use the GHL conversation timestamps, not a stopwatch. |
| 9 | Submit the website form. | Text-back within 30 seconds; opportunity in *New Lead*. |
| 10 | Book 25 hours ahead. | 24 h reminder arrives; then cancel and confirm the 1 h reminder does **not** send. |
| 11 | Stop the server, make a call, start it again. | `reconcile` lists the call as missing (exit 1). Then re-send or enter it, and reconcile exits 0. |
| 12 | Reply STOP to a text-back. | Contact has DND on; no reminder or text-back follows. |

Re-run 1, 2, and 6 after any prompt change. Small prompt edits break flows that were already working.
