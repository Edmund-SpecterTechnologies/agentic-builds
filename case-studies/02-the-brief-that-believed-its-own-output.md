# The brief that believed its own output

*Debugging an LLM-generated daily business brief that kept fabricating, and why "use transcripts,
not summaries" wasn't enough.*

## The system

Every morning a script collects the business's data (CRM pipeline, conversations, website traffic,
meeting transcripts, team chat) into SQLite, assembles it into a prompt with the company's context
files, and asks a model for a one-page brief: what moved, what needs attention, what it means for
the strategy. It is delivered to a team chat channel.

It fabricated three times. Each fix made sense at the time, and each time it came back.

## Round one: the loop

The third recurrence was different: the fabrications were escalating instead of fading. The cause
was structural. **The brief was delivered into the chat channel, and the chat loader read that
channel back in as an input.** The table held 110 rows: 109 posted by the delivery bot, 56 of them
containing "Daily Brief", and exactly one written by a human. Anything a brief asserted came back
the next day as a "signal from the team" and could be laundered into a fact.

Three more bugs sat underneath it:

- **Stale rows read as breaking news** because the loader dropped the dates. A deal three weeks old
  opened a brief as "a monumental win". Every row carried `created_at` and `updated_at`; the prompt
  got neither. Now the pipeline block is labelled as a standing total, and a separate block lists
  only what changed in the last seven days, with dates, or says NONE.
- **The brief invented a pricing rule and then flagged a violation of it**, comparing two different
  products as if they were one. None of the context files it loaded contained a client fact.
- **The file that would have prevented that was silently missing.** `read_text()` used the Windows
  default encoding, the pricing file failed on it at byte 1,295, and a bare `except Exception: pass`
  dropped it without a word. The source of truth for every price was absent from the brief that
  invented a pricing rule. Now it reads UTF-8, and a failed context file warns instead of vanishing.

## Round two: a genuine transcript of something that didn't happen

Weeks later, the brief reported six cold calls as real prospect conversations: targeting decisions,
a compliance violation, two booked appointments. None of it happened. **They were practice
roleplays against an AI sales coach.**

The existing safeguard was "transcripts only, never the meeting tool's AI summaries." It didn't
help, **because the transcripts were genuine**. A real transcript of a simulation is still a
simulation. Every roleplay also passed the old "read the first 300 characters" sanity check. Yet the
evidence was sitting in the text the model read: `end practice`, `stepping out of the call. Want
your feedback?`

Meanwhile the deterministic call counter said zero calls that day, and it was right.

**The fix, at two layers:**

1. The transcript classifier tags practice sessions using the coach's break-character phrases
   **plus same-day session clustering**. The clustering matters: 4 of the 12 roleplays were cut off
   before the coach's wrap-up and contained no marker at all. They were only catchable as part of a
   run of sessions on the same day.
2. The brief's transcript loader drops practice sessions with its own copy of the check, so a
   misclassification upstream doesn't reach the prompt.

Backfilled: **12 of 39 transcripts tagged, 0 real meetings touched.**

## Round three: model choice was never tested

Every fix so far had been a grounding rule in the prompt. None tested the model. The brief ran on
`gemini-2.5-flash`, a small, low-cost model, doing synthesis over sparse, messy data. I
added routing by model name so it can run on Claude, and kept the old default because the same
module ships to client installs that may only hold a Gemini key.

Two things I didn't expect:

- **The "easy upgrade" was closed.** The planned one-line switch to a larger Gemini model returned
  404 ("no longer available to new users") and the next one returned a quota of zero on the free
  tier. Moving to Claude turned out to be less friction than upgrading Gemini.
- **Cost estimates assumed identical token counts, and they aren't.** The same prompt tokenized to
  about 17K on Claude against 12K on Gemini. One real run cost $0.058, about $1.74 a month.

## What I took from it

- An LLM pipeline that reads its own output will eventually believe it. Check every input's
  provenance, including the ones you wrote.
- "Use the primary source" is necessary and not sufficient. The primary source can be a faithful
  record of something fake.
- A silent `except: pass` around context loading turns a missing fact into a confident invention.
- When a defect has recurred, one clean run proves nothing. Say how many clean runs would close it.
