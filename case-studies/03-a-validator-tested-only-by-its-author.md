# A validator tested only by its author fails open

*Building a lead-research pipeline where the LLM writes as little as possible, and what the
verifier found in the first batch anyway.*

## The goal

One sentence in ("find 25 growing businesses in Tampa Bay"), a review queue of outbound emails out.
**Nothing sends and nothing touches the CRM.** A human approves every row.

## Where the LLM is, and where it isn't

The most important design decision was keeping the model's role small:

- **Finding facts is deterministic Python.** A call-reason finder crawls each business's website and
  reviews and keeps *verbatim* quotes: posted hours, "24/7" claims, reviews that mention phones. A
  decision-maker finder cross-checks the state business registry against each company's own
  website. Run against existing prospect lists, the first found usable reasons for 259 of 418
  companies, and the second named a contact for 230 of 262.
- **The email is written by a human.** The model only fills short slots (ten words or fewer), and
  only from the verbatim evidence.
- **A checker script gates every slot** against its source before anything reaches the queue.
- **An observation is a reason to ask, never proof of a problem.** "Your site lists hours until 5pm"
  can open a conversation. It cannot become "you're missing calls after 5".

Claude runs the whole thing as a skill, so the orchestration is agentic while the parts that must
be exact are not.

## What the verifier found

Before any of it was used, the queue went to the `verifier` subagent (Opus, maximum effort; see
[case study 01](01-cheap-retrieval-expensive-judgment.md)). **It disproved the first batch.** Every
quote was real, and the batch was still wrong:

- The email template said "I help Tampa Bay businesses handle front-office phone calls." That was a
  service not yet delivered to anyone. It now describes what is actually built.
- 4 firms had been renamed, 2 absorbed or redirected, and 1 contact was in another state.
- 2 leads were already in the CRM. Dedup matched on email, and 80% of CRM contacts have no email.
- **20 of 20 constructed slots bypassed the checker.**
- The final renderer trusted a hand-typed PASS instead of re-running the check.

## The fixes

- Dedup by domain and company name, not just email.
- The checker hardened against a **31-case fixture** in which every known bypass now fails.
- The renderer re-runs the check itself instead of trusting an upstream flag.
- The template claim rewritten to something true today.

After the fixes: 5 rows ready and 2 on the fallback template. Total data cost for the batch: $0.15.

## The lesson

**A validator that has only been tested by its author fails open.** I wrote the checker, I wrote
the slots, and I believed the checker because my slots passed it. It took an adversary whose only
job was to break the claim to find that every slot went around it.

It also changed where I trust models. The ingredient that failed wasn't the model's writing. It was
my assumption that a check which raised no error had actually checked something.
