# How the CRM's design was chosen

Before rebuilding the CRM's interface, I researched how current CRMs handle the same problem, then
prototyped five directions that each answer a different question about what a CRM is *for*, rather
than five colour schemes on one layout. All five use the same fictional data, so the only thing
that differs is the design.

Open [`index.html`](index.html) to click through them. Each is a single self-contained HTML file.

| # | Direction | The question it answers | Drawn from |
|---|---|---|---|
| 1 | [**Ledger**](1-ledger/index.html) ✅ | What if the CRM were a spreadsheet you could trust? | Attio, Folk, Airtable |
| 2 | [**Board**](2-board/index.html) | What if every deal had to have a next step? | Pipedrive's activity-based selling and "rotting" deals |
| 3 | [**Today**](3-today/index.html) | What if it opened to who needs you, not to a database? | Close's focus on what to do next |
| 4 | [**Command**](4-command/index.html) | What if you never touched the mouse? | Linear and Twenty's command palette |
| 5 | [**Pocket**](5-pocket/index.html) | What if the owner runs the business from a truck? | Mobile field-service CRMs |

**Ledger was chosen and built.** It is now the real interface in [`../crm/`](../crm/), wired to the
API and covered by a 27-step browser check. The mockup here is the prototype it grew from.

## What the research said

- The most common reason people abandon a CRM is data entry that serves someone else's dashboard
  and gives nothing back to the person typing. That argues for less typing and more in-place
  editing, which is where Ledger and Pocket differ most from a traditional CRM.
- Pipedrive flags deals that haven't moved in a set number of days ("rotting"). Ledger keeps that
  idea as "going cold", shown in the table instead of on cards.
- Modern CRMs such as Twenty pair a table view with a kanban board and a command menu. Ledger keeps
  all three.

## Testing the mockups

Each mockup was opened in a real browser and its main interaction exercised before it was shown.
That caught three problems in the prototypes themselves: a pinned table column sliding over its
neighbour and hiding the stage colour, a command palette that couldn't find a person's own deal
by their name, and a palette that opened on arrival and blurred the whole screen.

## Sources

- [CRM Design Best Practices, Aufait UX](https://www.aufaitux.com/blog/crm-ux-design-best-practices/)
- [8 CRM UX Design Best Practices, Design Studio](https://www.designstudiouiux.com/blog/crm-ux-design-best-practices/)
- [Attio vs Folk comparison, Stacksync](https://www.stacksync.com/blog/attio-vs-folk-next-gen-crm-face-off-2025)
- [The Rotting feature, Pipedrive Knowledge Base](https://support.pipedrive.com/en/article/the-rotting-feature)
- [Activities & Goals, Pipedrive](https://www.pipedrive.com/en/features/activities-goals)
- [Close CRM for Sales Reps](https://close.com/persona-sales-rep)
- [Twenty CRM](https://twenty.com/)
- [Mobile CRM for small business, Method](https://www.method.me/blog/mobile-crm/)
- [Why CRM adoption fails, Atypical Tech](https://atypicaltech.com/en/blog/the-sales-team-wont-use-it)
