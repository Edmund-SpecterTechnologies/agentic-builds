# Agentic builds

Work I've built with AI coding agents, mostly Claude Code, while running an AI automation
consultancy. The code here is the part that can be public. The case studies cover the part that
can't: a private workspace that runs the business's data collection, research, and client builds.

I'm Edmund Squires. Before this I spent 15+ years in defense and intelligence, as a U.S. Army
intelligence analyst and then at Booz Allen Hamilton, where more and more of my work became building
tools that took manual work off analysts.
[LinkedIn](https://www.linkedin.com/in/edmundsquires)

## What's here

| | What it is | Why it's interesting |
|---|---|---|
| [**crm/**](crm/) | A full-stack local CRM (FastAPI, SQLite, plain JavaScript) with fictional demo data | Built with Claude Code. The interface was picked from five prototyped designs. Includes localhost attack defences, tested by running each attack at the app, and API and browser checks you can run. |
| [**case-studies/**](case-studies/) | Four write-ups from the private workspace and a client build | What went wrong with LLM systems in real use, and what fixed it. |
| [**design-options/**](design-options/) | Five clickable CRM design prototypes | How the CRM's interface was chosen: research first, then five directions that each answer a different question about what a CRM is for. |

### Case studies

1. [**Retrieval can be cheap. Interpretation cannot.**](case-studies/01-cheap-retrieval-expensive-judgment.md)
   Routing work across seven subagents, and why verification gets the most expensive model.
2. [**The brief that believed its own output.**](case-studies/02-the-brief-that-believed-its-own-output.md)
   An LLM daily brief that fabricated three times: a feedback loop, a silently dropped file, and a
   genuine transcript of a practice roleplay.
3. [**A validator tested only by its author fails open.**](case-studies/03-a-validator-tested-only-by-its-author.md)
   A lead-research pipeline that keeps the model's role small, and the verifier that disproved its
   first batch anyway.
4. [**The bot said it would stop. That isn't evidence it did.**](case-studies/04-the-bot-said-it-would-stop.md)
   An AI texting bot whose reply and actions came from separate layers and disagreed, why opt-out
   tests assert on stored state, and the passing test that found a race nobody was looking for.

## How I work with coding agents

These are habits from building a real system, not a checklist I read somewhere. Each one exists
because something went wrong without it.

- **The project instruction file is institutional memory.** Updating it is part of finishing any
  change, so the next session starts knowing what this one learned.
- **Plan before build.** Anything structural gets a written plan first, then gets executed against
  it. Reviewing the plan is where I catch a confidently wrong assumption most cheaply.
- **Corrections become rules, with the reason attached.** "Run `date` before writing any date"
  exists because an agent inferred today from `git log`, the last commit was two days old, and
  fifteen wrong dates went into three documents.
- **"Confirmed" without a method is unverified.** Every check records how it was done and what that
  method couldn't see. A six-day-old "confirmed" claim was disproved by one live test.
- **Never trust absence from a view that can't show it.** API list endpoints truncate silently, and
  builder UIs hide collapsed branches. "I didn't see it" is not "it isn't there."
- **Deterministic code where exactness matters, the model where judgment helps.** The research
  pipeline finds facts with plain Python and lets the model fill ten-word slots, gated by a checker.
- **Agent advice gets checked like anyone's.** A recommended "one-line model upgrade" turned out to
  404, and a report's "contacted, never replied" count turned out to be counting CRM record creation
  as outreach. Both read as plausible, and both were wrong.

## Running the code

Setup steps, the security model, and the tests are in [crm/README.md](crm/README.md). The CRM is
local-only by design, so read its security section before running it anywhere but your own machine.

## License

MIT. See [LICENSE](LICENSE).
