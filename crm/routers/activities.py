import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from ..db import get_db
from ..models import ActivityCreate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/activities")
def list_activities(
    contact_id: str = Query(default=""),
    opportunity_id: str = Query(default=""),
    type: str = Query(default=""),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
):
    with get_db() as conn:
        where_clauses: list[str] = []
        params: list = []
        if contact_id:
            where_clauses.append("contact_id = ?")
            params.append(contact_id)
        if opportunity_id:
            where_clauses.append("opportunity_id = ?")
            params.append(opportunity_id)
        if type:
            where_clauses.append("type = ?")
            params.append(type)
        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        rows = conn.execute(
            f"SELECT * FROM activities {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [dict(r) for r in rows]


@router.post("/activities", status_code=201)
def create_activity(body: ActivityCreate):
    aid = str(uuid.uuid4())
    now = _now()
    contact_name = None
    opportunity_name = None
    with get_db() as conn:
        if body.contact_id:
            row = conn.execute(
                "SELECT first_name, last_name FROM contacts WHERE id = ?", (body.contact_id,)
            ).fetchone()
            if row:
                parts = [row["first_name"] or "", row["last_name"] or ""]
                contact_name = " ".join(p for p in parts if p).strip() or None
        if body.opportunity_id:
            row = conn.execute(
                "SELECT name FROM opportunities WHERE id = ?", (body.opportunity_id,)
            ).fetchone()
            if row:
                opportunity_name = row["name"]
        conn.execute(
            """INSERT INTO activities
               (id, type, body, contact_id, contact_name, opportunity_id, opportunity_name, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (aid, body.type, body.body, body.contact_id, contact_name,
             body.opportunity_id, opportunity_name, now),
        )
        row = conn.execute("SELECT * FROM activities WHERE id = ?", (aid,)).fetchone()
        return dict(row)


@router.delete("/activities/{activity_id}", status_code=204)
def delete_activity(activity_id: str):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM activities WHERE id = ?", (activity_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Activity not found")
        conn.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
