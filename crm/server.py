import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .db import get_db, init_db
from .routers import contacts, companies, pipelines, opportunities, activities, tasks, saved_views

@asynccontextmanager
async def lifespan(app):
    init_db()
    _seed_default_pipeline()
    yield


app = FastAPI(title="Specter CRM", lifespan=lifespan)

# ── Local-only request guards ─────────────────────────────────────────────────
# The CRM has no login because it only listens on 127.0.0.1. Two browser attacks
# can still reach a localhost app from a page on another site:
#   1. DNS rebinding: an attacker's domain re-resolves to 127.0.0.1, so their page
#      becomes "same-origin" with this server and can read every record. Rejecting
#      any Host header that isn't localhost closes that.
#   2. Cross-site writes: a hostile page submits a form or text/plain POST. Recent
#      FastAPI rejects non-JSON bodies, but older versions parse them, so writes
#      from a foreign Origin are refused here regardless of framework version.
PORT = int(os.environ.get("CRM_PORT", "8090"))
ALLOWED_ORIGINS = {f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])


@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error(request: Request, exc: sqlite3.IntegrityError):
    # e.g. a contact pointing at a company id that doesn't exist. That's bad
    # input, not a server fault, so answer 400 instead of a bare 500.
    return JSONResponse({"detail": f"Invalid reference or constraint: {exc}"}, status_code=400)


@app.middleware("http")
async def reject_cross_site_writes(request: Request, call_next):
    origin = request.headers.get("origin")
    # No Origin header means a non-browser client (curl, a script); browsers
    # always send one on cross-origin POST/PUT/PATCH/DELETE.
    if request.method not in SAFE_METHODS and origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
    return await call_next(request)


app.include_router(contacts.router, prefix="/api")
app.include_router(companies.router, prefix="/api")
app.include_router(pipelines.router, prefix="/api")
app.include_router(opportunities.router, prefix="/api")
app.include_router(activities.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(saved_views.router, prefix="/api")

CRM_DIR = Path(__file__).parent

DEFAULT_STAGES = [
    ("New Lead",       "#6B7280"),
    ("Contacted",      "#3B82F6"),
    ("Qualified",      "#8B5CF6"),
    ("Proposal Sent",  "#F59E0B"),
    ("Won",            "#10B981"),
    ("Lost",           "#EF4444"),
]


def _seed_default_pipeline():
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM pipelines").fetchone()[0]
        if count > 0:
            return
        pid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO pipelines (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (pid, "Sales Pipeline", now, now),
        )
        for position, (name, color) in enumerate(DEFAULT_STAGES):
            conn.execute(
                "INSERT INTO pipeline_stages (id, pipeline_id, name, position, color, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), pid, name, position, color, now, now),
            )


@app.get("/")
async def root():
    return HTMLResponse((CRM_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/dashboard")
async def dashboard():
    with get_db() as conn:
        total_contacts = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        total_companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        open_row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(monetary_value), 0) FROM opportunities WHERE status = 'open'"
        ).fetchone()
        won_count = conn.execute(
            "SELECT COUNT(*) FROM opportunities WHERE status = 'won'"
        ).fetchone()[0]
        # Win rate is won out of closed deals; open deals haven't been decided yet.
        closed = conn.execute(
            "SELECT COUNT(*) FROM opportunities WHERE status IN ('won','lost')"
        ).fetchone()[0]
        win_rate = round(won_count / closed * 100, 1) if closed > 0 else 0

        pipeline_rows = conn.execute("SELECT id, name FROM pipelines ORDER BY created_at").fetchall()
        pipeline_breakdown = []
        for p in pipeline_rows:
            stages = conn.execute(
                """SELECT ps.name, COUNT(o.id) as count, COALESCE(SUM(o.monetary_value), 0) as value
                   FROM pipeline_stages ps
                   LEFT JOIN opportunities o ON o.stage_id = ps.id AND o.status = 'open'
                   WHERE ps.pipeline_id = ?
                   GROUP BY ps.id
                   ORDER BY ps.position""",
                (p["id"],),
            ).fetchall()
            pipeline_breakdown.append(
                {
                    "pipeline_id": p["id"],
                    "pipeline_name": p["name"],
                    "stages": [dict(s) for s in stages],
                }
            )

    return {
        "total_contacts": total_contacts,
        "total_companies": total_companies,
        "open_opportunities": open_row[0],
        "pipeline_value": open_row[1],
        "won_count": won_count,
        "win_rate": win_rate,
        "pipelines": pipeline_breakdown,
    }


@app.get("/api/search")
async def search(q: str = "", limit: int = 5):
    if not q or len(q.strip()) < 2:
        return {"contacts": [], "companies": [], "opportunities": []}
    like = f"%{q.strip()}%"
    with get_db() as conn:
        contacts_rows = conn.execute(
            """SELECT id, first_name, last_name, email, phone, company_name
               FROM contacts
               WHERE first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR phone LIKE ? OR company_name LIKE ?
               ORDER BY created_at DESC LIMIT ?""",
            (like, like, like, like, like, limit),
        ).fetchall()
        companies_rows = conn.execute(
            """SELECT id, name, industry, website
               FROM companies
               WHERE name LIKE ? OR industry LIKE ? OR website LIKE ?
               ORDER BY created_at DESC LIMIT ?""",
            (like, like, like, limit),
        ).fetchall()
        opps_rows = conn.execute(
            """SELECT id, name, stage_name, pipeline_name, monetary_value, status, contact_name
               FROM opportunities
               WHERE name LIKE ? OR contact_name LIKE ? OR company_name LIKE ?
               ORDER BY created_at DESC LIMIT ?""",
            (like, like, like, limit),
        ).fetchall()
    return {
        "contacts": [dict(r) for r in contacts_rows],
        "companies": [dict(r) for r in companies_rows],
        "opportunities": [dict(r) for r in opps_rows],
    }


@app.get("/api/reports")
async def reports():
    from datetime import date, timedelta
    today = date.today().isoformat()
    thirty_days_ago = (date.today() - timedelta(days=30)).isoformat()

    with get_db() as conn:
        act_rows = conn.execute(
            "SELECT type, COUNT(*) as count FROM activities GROUP BY type ORDER BY count DESC"
        ).fetchall()
        activity_by_type = [dict(r) for r in act_rows]

        monthly_rows = conn.execute(
            """SELECT substr(created_at, 1, 7) as month, COUNT(*) as count
               FROM activities
               WHERE created_at >= date('now', '-6 months')
               GROUP BY month ORDER BY month ASC"""
        ).fetchall()
        monthly_activities = [dict(r) for r in monthly_rows]

        src_rows = conn.execute(
            """SELECT COALESCE(source, 'Unknown') as source, COUNT(*) as count
               FROM contacts GROUP BY source ORDER BY count DESC"""
        ).fetchall()
        contacts_by_source = [dict(r) for r in src_rows]

        open_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'open'").fetchone()[0]
        done_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'done'").fetchone()[0]
        overdue_count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'open' AND due_date IS NOT NULL AND due_date < ?",
            (today,),
        ).fetchone()[0]
        tasks_summary = {"open": open_count, "done": done_count, "overdue": overdue_count}

        recent_act_count = conn.execute(
            "SELECT COUNT(*) FROM activities WHERE created_at >= ?", (thirty_days_ago,)
        ).fetchone()[0]

    return {
        "activity_by_type": activity_by_type,
        "monthly_activities": monthly_activities,
        "contacts_by_source": contacts_by_source,
        "tasks_summary": tasks_summary,
        "recent_activity_count": recent_act_count,
    }


if __name__ == "__main__":
    uvicorn.run("crm.server:app", host="127.0.0.1", port=PORT, reload=False)
