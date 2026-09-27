import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from ..db import get_db
from ..models import TaskCreate, TaskUpdate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_names(conn, contact_id, opportunity_id):
    contact_name = None
    opportunity_name = None
    if contact_id:
        row = conn.execute(
            "SELECT first_name, last_name FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()
        if row:
            parts = [row["first_name"] or "", row["last_name"] or ""]
            contact_name = " ".join(p for p in parts if p).strip() or None
    if opportunity_id:
        row = conn.execute(
            "SELECT name FROM opportunities WHERE id = ?", (opportunity_id,)
        ).fetchone()
        if row:
            opportunity_name = row["name"]
    return contact_name, opportunity_name


@router.get("/tasks")
def list_tasks(
    contact_id: str = Query(default=""),
    opportunity_id: str = Query(default=""),
    status: str = Query(default=""),
    limit: int = Query(default=200),
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
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        rows = conn.execute(
            f"SELECT * FROM tasks {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [dict(r) for r in rows]


@router.post("/tasks", status_code=201)
def create_task(body: TaskCreate):
    tid = str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        contact_name, opportunity_name = _resolve_names(conn, body.contact_id, body.opportunity_id)
        conn.execute(
            """INSERT INTO tasks
               (id, title, due_date, status, contact_id, contact_name,
                opportunity_id, opportunity_name, assigned_to, notes, created_at, updated_at)
               VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tid, body.title, body.due_date,
             body.contact_id, contact_name,
             body.opportunity_id, opportunity_name,
             body.assigned_to, body.notes, now, now),
        )
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
        return dict(row)


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return dict(row)


@router.put("/tasks/{task_id}")
def update_task(task_id: str, body: TaskUpdate):
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")
        current = dict(existing)
        now = _now()
        sent = body.model_fields_set  # sent-but-blank means unlink; not sent means keep
        new_contact_id = body.contact_id if "contact_id" in sent else current.get("contact_id")
        new_opp_id = body.opportunity_id if "opportunity_id" in sent else current.get("opportunity_id")
        contact_name, opportunity_name = _resolve_names(conn, new_contact_id, new_opp_id)
        conn.execute(
            """UPDATE tasks SET
               title = ?, due_date = ?, status = ?,
               contact_id = ?, contact_name = ?,
               opportunity_id = ?, opportunity_name = ?,
               assigned_to = ?, notes = ?, updated_at = ?
               WHERE id = ?""",
            (
                body.title if body.title is not None else current["title"],
                body.due_date if "due_date" in sent else current.get("due_date"),
                body.status if body.status is not None else current["status"],
                new_contact_id, contact_name,
                new_opp_id, opportunity_name,
                body.assigned_to if body.assigned_to is not None else current.get("assigned_to"),
                body.notes if body.notes is not None else current.get("notes"),
                now,
                task_id,
            ),
        )
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row)


@router.patch("/tasks/{task_id}/complete")
def toggle_task(task_id: str):
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")
        new_status = "done" if existing["status"] == "open" else "open"
        now = _now()
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, task_id),
        )
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
