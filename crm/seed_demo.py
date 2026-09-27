"""Load a fictional demo dataset into the CRM.

Everything here is invented: companies use example.com domains and phone numbers
use 555-0100 through 555-0199, the range reserved for fictional use. Records are created through the same
handler functions the HTTP API calls, with the same Pydantic models, so the demo
data passes the same validation a user's input would. No server needs to be running.

Afterwards, timestamps are backdated so the data looks lived-in: each deal's last
activity is days or weeks old, which is what makes "Going cold" and "Last touch"
show something real. That step is plain SQL, because the API always stamps "now".

Usage (from the repo root):
    python -m crm.seed_demo            # seeds crm/crm.db if it has no contacts
    CRM_DB_PATH=/tmp/demo.db python -m crm.seed_demo
"""

from datetime import date, datetime, timedelta, timezone

from .db import DB_PATH, get_db, init_db
from .models import ActivityCreate, CompanyCreate, ContactCreate, OpportunityCreate, TaskCreate
from .routers import activities, companies, contacts, opportunities, pipelines, tasks
from .server import _seed_default_pipeline

COMPANIES = [
    ("Harborline Plumbing", "Plumbing", "harborline.example.com"),
    ("Northgate Dental Group", "Healthcare", "northgatedental.example.com"),
    ("Cedar & Pine Landscaping", "Landscaping", "cedarpine.example.com"),
    ("Brightwater Property Management", "Real Estate", "brightwater.example.com"),
    ("Summit Roofing Co.", "Roofing", "summitroofing.example.com"),
    ("Lumen Physical Therapy", "Healthcare", "lumenpt.example.com"),
]

# (first, last, company index, source, tags)
CONTACTS = [
    ("Dana", "Whitfield", 0, "Referral", ["owner"]),
    ("Marcus", "Ellery", 1, "Website", ["office-manager"]),
    ("Priya", "Sandoval", 2, "Cold email", ["owner"]),
    ("Tom", "Okafor", 3, "Referral", ["operations"]),
    ("Jenna", "Kowalski", 4, "Networking event", ["owner"]),
    ("Luis", "Ferreira", 5, "Website", ["practice-manager"]),
    ("Grace", "Holloway", 1, "Website", ["billing"]),
    ("Owen", "Brandt", 3, "Referral", ["owner"]),
]

# (name, contact index, stage name, value, notes)
OPPORTUNITIES = [
    ("After-hours call answering", 0, "New Lead", 497, "Misses calls after 5pm; owner answers from the truck."),
    ("Appointment reminders + recall", 1, "Contacted", 794, "Two locations. No-show rate is the pain."),
    ("Review request automation", 2, "Qualified", 297, "Wants more reviews before spring season."),
    ("Tenant request intake", 3, "Proposal Sent", 1497, "Maintenance requests arrive by text, email, and voicemail."),
    ("Storm-season lead capture", 4, "Qualified", 997, "Inbound spikes after storms; calls go to voicemail."),
    ("New patient intake forms", 5, "Won", 1297, "Signed. Kickoff scheduled."),
    ("Billing follow-up workflow", 6, "Contacted", 497, "Interested but wants to see a demo first."),
    ("Owner reporting dashboard", 7, "Lost", 1997, "Chose to wait until Q1 budget."),
]

# Days since each contact's last touch, by contact index. 7+ days reads as "going cold".
LAST_TOUCH_DAYS = [2, 9, 1, 12, 0, 3, 15, 20]

# (type, contact index, body)
ACTIVITIES = [
    ("call", 0, "Intro call. Busiest months are June to September."),
    ("email", 1, "Sent summary of the reminder workflow and pricing."),
    ("note", 2, "Competitors nearby have 3-4x the review count."),
    ("call", 3, "Walked through current intake. 40+ requests a week."),
    ("sms", 4, "Confirmed demo for Thursday 10am."),
    ("note", 5, "Contract signed. Needs EHR export format."),
    ("call", 7, "Not this quarter. Follow up in January."),
]

# (title, contact index, days from today, notes)
TASKS = [
    ("Send proposal", 2, 1, "Include the review-count comparison."),
    ("Follow up on proposal", 3, -2, "No reply yet."),
    ("Prep demo", 4, 3, None),
    ("Kickoff call", 5, 5, "Bring intake form draft."),
    ("Check in", 7, 90, "Q1 budget cycle."),
]


def backdate(contact_ids, opp_ids) -> None:
    now = datetime.now(timezone.utc)
    stamp = lambda days: (now - timedelta(days=days)).isoformat()
    with get_db() as conn:
        for ci, days in enumerate(LAST_TOUCH_DAYS):
            created = stamp(days + 14 + ci * 3)
            conn.execute("UPDATE contacts SET created_at = ?, updated_at = ? WHERE id = ?", (created, created, contact_ids[ci]))
            conn.execute("UPDATE opportunities SET created_at = ?, updated_at = ? WHERE id = ?", (created, stamp(days), opp_ids[ci]))
            conn.execute("UPDATE activities SET created_at = ? WHERE contact_id = ?", (stamp(days), contact_ids[ci]))


def seed() -> None:
    init_db()
    _seed_default_pipeline()
    with get_db() as conn:
        if conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]:
            print(f"{DB_PATH} already has contacts; not seeding. Set CRM_DB_PATH to a new file to seed fresh.")
            return

    company_ids = []
    for i, (name, industry, domain) in enumerate(COMPANIES):
        co = companies.create_company(CompanyCreate(
            name=name, industry=industry, website=f"https://{domain}", phone=f"(201) 555-01{i:02d}"))
        company_ids.append(co["id"])

    contact_ids = []
    for i, (first, last, co, source, tags) in enumerate(CONTACTS):
        c = contacts.create_contact(ContactCreate(
            first_name=first, last_name=last, email=f"{first.lower()}@{COMPANIES[co][2]}",
            phone=f"(201) 555-01{20 + i:02d}", company_id=company_ids[co], source=source, tags=tags))
        contact_ids.append(c["id"])

    pipeline = pipelines.list_pipelines()[0]
    stages = {s["name"]: s["id"] for s in pipeline["stages"]}
    opp_ids = []
    for name, ci, stage, value, notes in OPPORTUNITIES:
        o = opportunities.create_opportunity(OpportunityCreate(
            name=name, contact_id=contact_ids[ci], company_id=company_ids[CONTACTS[ci][2]],
            pipeline_id=pipeline["id"], stage_id=stages[stage],
            status={"Won": "won", "Lost": "lost"}.get(stage, "open"), monetary_value=value, notes=notes))
        opp_ids.append(o["id"])

    for kind, ci, body in ACTIVITIES:
        activities.create_activity(ActivityCreate(
            type=kind, body=body, contact_id=contact_ids[ci], opportunity_id=opp_ids[ci]))

    backdate(contact_ids, opp_ids)

    today = date.today()
    for title, ci, days, notes in TASKS:
        tasks.create_task(TaskCreate(
            title=title, due_date=(today + timedelta(days=days)).isoformat(),
            contact_id=contact_ids[ci], opportunity_id=opp_ids[ci], notes=notes))

    print(f"Seeded {DB_PATH}: {len(COMPANIES)} companies, {len(CONTACTS)} contacts, "
          f"{len(OPPORTUNITIES)} opportunities, {len(ACTIVITIES)} activities, {len(TASKS)} tasks.")


if __name__ == "__main__":
    seed()
