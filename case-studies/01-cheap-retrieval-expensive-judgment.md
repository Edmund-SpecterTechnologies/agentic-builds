# Retrieval can be cheap. Interpretation cannot.

*How I route work across models in a Claude Code workspace, and why verification gets the most
expensive model instead of the cheapest.*

## The problem

My company's operations run in a Claude Code workspace: CRM data collectors, a daily business
brief, sales research pipelines, client build documentation. As it grew, everything ran on whatever
model the session happened to be using. That is wasteful in one direction (a frontier model reading
a database row) and dangerous in the other (a small model deciding what a number means).

Before choosing a split, I went back through the failures on record. Three separate systems had
produced confident, specific, wrong output:

- a meeting-recording tool's AI summaries (six documented fabrications, including two hours of
  background music titled as a business strategy meeting),
- the daily brief generator, which fabricated three times,
- structural claims about the CRM platform ("that workflow has no branch for X"), made from views
  that could not display X.

**Every one failed at the interpretation step. None failed at the fetch step.** Pulling a row, a
page, or a transcript was never the problem. Deciding what it meant was.

So the useful seam is not "important vs. unimportant work". It is **getting the data vs. saying what
it means.**

## The design

Seven subagents, each a Claude Code agent definition pinned to a model *and* an effort level:

| Agent | Model / effort | Job |
|---|---|---|
| `retrieval` | Haiku / low | Fetch and return verbatim. Forbidden from interpreting. |
| `analyst` | Sonnet / high | Compute from the databases. |
| `doc-builder` | Sonnet / medium | Build .docx/.xlsx/.pdf once content is settled. |
| `prose` | Fable / medium | Write copy in the company voice. |
| `researcher` | Opus / high | Go three levels deep on one question. |
| `strategist` | Opus / high | Decide: pricing, deal terms, approach. |
| `verifier` | **Opus / max** | Try to break a claim before it ships. |

Two of them are in [`agents/`](agents/), lightly sanitized.

**They are system prompts, not labels with a model attached.** Each carries the specific rules its
job depends on. `retrieval` holds the absence rule ("not present in the view I checked, which cannot
rule out...") and is told that writing "this suggests" means it has crossed into someone else's job.
`verifier` opens every check with "by what method?" and must record what its own method cannot see.

## The counterintuitive call: verification is the most expensive agent

The instinct is to make checking cheap, since you run it a lot. The record said otherwise. **Every
verification failure in this workspace failed open**: a check ran, raised no error, and was written
down as a pass. A cheap verifier confirms whatever it was handed. So the verifier runs on the most
capable model at maximum effort, and it is used sparingly: before anything ships to a client, before
a bot talks to a real person, and whenever an earlier session marked something "confirmed" without
recording how.

It has paid for itself. When it reviewed the first batch of outbound sales emails from a new research
pipeline, it disproved the batch (see [case study 03](03-a-validator-tested-only-by-its-author.md)).

## What I learned about the tooling

- I checked the agent-definition schema against Anthropic's official plugins before writing any of
  it, rather than assuming. `effort:` exists only in agent frontmatter; there is no effort parameter
  on an individual agent call. Skill frontmatter does not honor `model:` at all, so a skill that
  needs a specific model has to say so in its body, as instructions.
- I deliberately did **not** downgrade the command that writes the project changelog. That file is
  the workspace's institutional memory, and cheapening it would quietly degrade the most valuable
  prose the system produces.
- While doing this I found the daily brief wasn't running on Claude at all. It called a small, low-cost
  Gemini model for high-stakes synthesis over sparse data, which is the textbook setup for confident
  fabrication. See [case study 02](02-the-brief-that-believed-its-own-output.md).

## The tradeoff I'd flag

Routing adds a decision to every task: which agent? Most tasks still run in the main session. The
subagents earn their keep on the two ends of the range: bulk fetching, where a small model is
plenty, and verification or strategy, where a wrong answer is expensive. The middle is where the
judgment call lives, and I would rather make it explicitly than let the default decide.
