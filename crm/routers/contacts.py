import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from ..db import get_db
from ..models import ContactCreate, ContactUpdate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    d = dict(row)
    tags_raw = d.get("tags", "[]") or "[]"
    try:
        d["tags"] = json.loads(tags_raw)
    except Exception:
        d["tags"] = []
    return d


@router.get("/contacts")
def list_contacts(
    search: str = Query(default=""),
    status: str = Query(default=""),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
):
    with get_db() as conn:
        params: list = []
        where_clauses: list[str] = []

        if search:
            like = f"%{search}%"
            where_clauses.append(
                "(first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR phone LIKE ? OR company_name LIKE ?)"
            )
            params.extend([like, like, like, like, like])

        if status:
            where_clauses.append("status = ?")
            params.append(status)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        rows = conn.execute(
            f"SELECT * FROM contacts {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


@router.post("/contacts", status_code=201)
def create_contact(body: ContactCreate):
    cid = str(uuid.uuid4())
    now = _now()

    company_name = None
    if body.company_id:
        with get_db() as conn:
            co = conn.execute("SELECT name FROM companies WHERE id = ?", (body.company_id,)).fetchone()
            company_name = co["name"] if co else None

    with get_db() as conn:
        conn.execute(
            """INSERT INTO contacts
               (id, first_name, last_name, email, phone, company_id, company_name,
                tags, source, status, assigned_to, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cid, body.first_name, body.last_name, body.email, body.phone,
                body.company_id, company_name,
                json.dumps(body.tags), body.source, body.status,
                body.assigned_to, body.notes, now, now,
            ),
        )
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (cid,)).fetchone()
        return _row_to_dict(row)


@router.get("/contacts/{contact_id}")
def get_contact(contact_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Contact not found")
        return _row_to_dict(row)


@router.put("/contacts/{contact_id}")
def update_contact(contact_id: str, body: ContactUpdate):
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Contact not found")

        current = _row_to_dict(existing)
        now = _now()

        # A field that was sent blank (now None) means "unlink"; a field that was
        # not sent at all means "leave as is". model_fields_set tells them apart.
        company_name = current.get("company_name")
        new_company_id = body.company_id if "company_id" in body.model_fields_set else current.get("company_id")
        if new_company_id != current.get("company_id"):
            co = conn.execute("SELECT name FROM companies WHERE id = ?", (new_company_id,)).fetchone() if new_company_id else None
            company_name = co["name"] if co else None

        new_tags = body.tags if body.tags is not None else current.get("tags", [])

        conn.execute(
            """UPDATE contacts SET
               first_name = ?, last_name = ?, email = ?, phone = ?,
               company_id = ?, company_name = ?, tags = ?,
               source = ?, status = ?, assigned_to = ?, notes = ?, updated_at = ?
               WHERE id = ?""",
            (
                body.first_name if body.first_name is not None else current.get("first_name"),
                body.last_name if body.last_name is not None else current.get("last_name"),
                body.email if body.email is not None else current.get("email"),
                body.phone if body.phone is not None else current.get("phone"),
                new_company_id,
                company_name,
                json.dumps(new_tags),
                body.source if body.source is not None else current.get("source"),
                body.status if body.status is not None else current.get("status"),
                body.assigned_to if body.assigned_to is not None else current.get("assigned_to"),
                body.notes if body.notes is not None else current.get("notes"),
                now,
                contact_id,
            ),
        )
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        # Deals, tasks, and activities store the contact's name for fast listing,
        # so a rename has to reach them too (companies already do the same).
        new_name = " ".join(p for p in (row["first_name"] or "", row["last_name"] or "") if p).strip() or None
        old_name = " ".join(p for p in (current.get("first_name") or "", current.get("last_name") or "") if p).strip() or None
        if new_name != old_name:
            for table in ("opportunities", "tasks", "activities"):
                conn.execute(f"UPDATE {table} SET contact_name = ? WHERE contact_id = ?", (new_name, contact_id))
        return _row_to_dict(row)


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: str):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Contact not found")
        # The foreign keys null the ids; clear the stored names too, or linked
        # deals, tasks, and activities keep showing someone who no longer exists.
        for table in ("opportunities", "tasks", "activities"):
            conn.execute(f"UPDATE {table} SET contact_name = NULL WHERE contact_id = ?", (contact_id,))
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
