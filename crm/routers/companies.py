import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from ..db import get_db
from ..models import CompanyCreate, CompanyUpdate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _contact_to_dict(row) -> dict:
    d = dict(row)
    tags_raw = d.get("tags", "[]") or "[]"
    try:
        d["tags"] = json.loads(tags_raw)
    except Exception:
        d["tags"] = []
    return d


@router.get("/companies")
def list_companies(
    search: str = Query(default=""),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
):
    with get_db() as conn:
        params: list = []
        where_sql = ""
        if search:
            like = f"%{search}%"
            where_sql = "WHERE (name LIKE ? OR industry LIKE ?)"
            params.extend([like, like])
        rows = conn.execute(
            f"SELECT * FROM companies {where_sql} ORDER BY name LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [dict(r) for r in rows]


@router.post("/companies", status_code=201)
def create_company(body: CompanyCreate):
    cid = str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO companies
               (id, name, industry, website, phone, email, address, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cid, body.name, body.industry, body.website, body.phone,
             body.email, body.address, body.notes, now, now),
        )
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone()
        return dict(row)


@router.get("/companies/{company_id}")
def get_company(company_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Company not found")
        company = dict(row)
        contacts = conn.execute(
            "SELECT * FROM contacts WHERE company_id = ? ORDER BY created_at DESC",
            (company_id,),
        ).fetchall()
        company["contacts"] = [_contact_to_dict(c) for c in contacts]
        return company


@router.put("/companies/{company_id}")
def update_company(company_id: str, body: CompanyUpdate):
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Company not found")
        current = dict(existing)
        now = _now()

        new_name = body.name if body.name is not None else current["name"]
        conn.execute(
            """UPDATE companies SET
               name = ?, industry = ?, website = ?, phone = ?, email = ?, address = ?, notes = ?, updated_at = ?
               WHERE id = ?""",
            (
                new_name,
                body.industry if body.industry is not None else current.get("industry"),
                body.website if body.website is not None else current.get("website"),
                body.phone if body.phone is not None else current.get("phone"),
                body.email if body.email is not None else current.get("email"),
                body.address if body.address is not None else current.get("address"),
                body.notes if body.notes is not None else current.get("notes"),
                now,
                company_id,
            ),
        )
        if body.name is not None and body.name != current["name"]:
            conn.execute(
                "UPDATE contacts SET company_name = ?, updated_at = ? WHERE company_id = ?",
                (new_name, now, company_id),
            )
            conn.execute(
                "UPDATE opportunities SET company_name = ?, updated_at = ? WHERE company_id = ?",
                (new_name, now, company_id),
            )
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        company = dict(row)
        contacts = conn.execute(
            "SELECT * FROM contacts WHERE company_id = ? ORDER BY created_at DESC",
            (company_id,),
        ).fetchall()
        company["contacts"] = [_contact_to_dict(c) for c in contacts]
        return company


@router.delete("/companies/{company_id}", status_code=204)
def delete_company(company_id: str):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Company not found")
        conn.execute(
            "UPDATE contacts SET company_id = NULL, company_name = NULL WHERE company_id = ?",
            (company_id,),
        )
        conn.execute("UPDATE opportunities SET company_name = NULL WHERE company_id = ?", (company_id,))
        conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))
