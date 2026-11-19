# The post-call sync as a Make.com scenario

Some agencies want every integration in Make so that non-developers can see and change it. This is
the same post-call sync as [receptionist/sync.py](../receptionist/sync.py), with the same failure
rules, laid out as Make modules. It is a design, not an exported blueprint.

## Where Make fits and where it doesn't

- **Post-call sync: good fit.** Nobody is waiting on it, and Make's error routes and stored incomplete
  executions map directly onto the retry and dead-letter rules.
- **Live booking tools: keep in code.** The caller is on the line while the tool runs. Make adds
  queueing and per-module latency you don't control, and a Vapi tool reply must come back as HTTP 200
  with a result or the assistant hears "no result returned." Use the server's
  [tools.py](../receptionist/tools.py) for this part.

## Scenario: `Vapi end-of-call → GHL`

| # | Module | Notes |
|---|---|---|
| 1 | Webhooks › Custom webhook | Turn on **Get request headers**. Point the assistant's server URL here. |
| 2 | Filter | Header `authorization` = `Bearer <secret>`, **and** `message.type` = `end-of-call-report`. Everything else stops here. |
| 3 | Data store › Get a record | Store `vapi_calls`, key = `message.call.id`. If it exists with `status = done`, stop. This is the duplicate-delivery guard. |
| 4 | Data store › Add/replace a record | `status = processing`, `received_at = now`. |
| 5 | HighLevel › Create/Update contact (or HTTP › `POST /contacts/upsert`) | Match on phone. Safe to repeat. |
| 6 | HTTP › `GET /contacts/{id}/notes` + Iterator + Filter | Look for `[vapi-call:<id>]` in existing note bodies. Only continue to 7 if it isn't there. |
| 7 | HTTP › `POST /contacts/{id}/notes` | Summary, transcript, recording URL, and the marker. |
| 8 | HTTP › `POST /opportunities/upsert` | Stage from the outcome (booked / emergency / new lead). |
| 9 | Data store › Get a record | If `owner_text = sending` from an earlier run, stop and alert: never resend. |
| 10 | Data store › Update a record | `owner_text = sending`. |
| 11 | HighLevel › Send SMS to the owner contact | |
| 12 | Data store › Update a record | `owner_text = done`, `status = done`. |

## Error routes

Turn on **Allow storing of incomplete executions** in the scenario settings. That is Make's
dead-letter queue: a failed run is kept with its data and can be resumed once the cause is fixed.

| Module | Error handler | Why |
|---|---|---|
| 5, 8 (safe to repeat) | **Break**, automatic retry on, 3 attempts, 5-minute interval | Rate limits and short outages fix themselves. |
| 7 (note) | **Break** with retry. Step 6 runs again on retry, so a note that landed before a timeout is found. | GHL notes have no idempotency key. |
| 11 (owner text) | **Break**, retry **off**, plus an alert route | A timed-out send may have gone out. A person checks before resending. |
| Any | An error route ending in Slack/email: call id, module, error text, and a link to the incomplete execution | Nobody should find out from the client. |

## The daily check still applies

Make only sees the webhooks that reach it. Run [reconcile.py](../receptionist/reconcile.py) (or a
second scheduled scenario: Vapi `GET /call` for yesterday compared against the `vapi_calls` data store)
to catch calls whose webhook never arrived.

## Confirm in the builder

Module names follow Make's HighLevel app and core modules at the time of writing. Confirm whether the
HighLevel app's contact module upserts on phone in the client's duplicate-contact setting. If it
doesn't, use the HTTP module against `/contacts/upsert`.
