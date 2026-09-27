import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from ..db import get_db
from ..models import OpportunityCreate, OpportunityUpdate, OpportunityStageUpdate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_for_stage(stage_name, current_status):
    """Keep status in step with the default Won/Lost stages.

    Moving a deal into a stage named Won or Lost closes it; moving a closed deal
    back into any other stage reopens it. Without this, dragging a card into "Won"
    left it counted as open pipeline on the dashboard.
    """
    name = (stage_name or "").strip().lower()
    if name in ("won", "lost"):
        return name
    return "open" if current_status in ("won", "lost") else current_status


def _resolve_names(conn, contact_id, company_id, pipeline_id, stage_id):
    contact_name = None
    if contact_id:
        row = conn.execute(
            "SELECT first_name, last_name FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()
        if row:
            parts = [row["first_name"] or "", row["last_name"] or ""]
            contact_name = " ".join(p for p in parts if p).strip() or None

    company_name = None
    if company_id:
        row = conn.execute("SELECT name FROM companies WHERE id = ?", (company_id,)).fetchone()
        if row:
            company_name = row["name"]

    pipeline_name = None
    if pipeline_id:
        row = conn.execute("SELECT name FROM pipelines WHERE id = ?", (pipeline_id,)).fetchone()
        if row:
            pipeline_name = row["name"]

    stage_name = None
    if stage_id:
        row = conn.execute("SELECT name FROM pipeline_stages WHERE id = ?", (stage_id,)).fetchone()
        if row:
            stage_name = row["name"]

    return contact_name, company_name, pipeline_name, stage_name


@router.get("/opportunities")
def list_opportunities(
    pipeline_id: str = Query(default=""),
    stage_id: str = Query(default=""),
    status: str = Query(default=""),
    search: str = Query(default=""),
    limit: int = Query(default=200),
    offset: int = Query(default=0),
):
    with get_db() as conn:
        where_clauses: list[str] = []
        params: list = []

        if pipeline_id:
            where_clauses.append("pipeline_id = ?")
            params.append(pipeline_id)
        if stage_id:
            where_clauses.append("stage_id = ?")
            params.append(stage_id)
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if search:
            like = f"%{search}%"
            where_clauses.append(
                "(name LIKE ? OR contact_name LIKE ? OR company_name LIKE ?)"
            )
            params.extend([like, like, like])

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        rows = conn.execute(
            f"SELECT * FROM opportunities {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [dict(r) for r in rows]


@router.post("/opportunities", status_code=201)
def create_opportunity(body: OpportunityCreate):
    oid = str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        p = conn.execute("SELECT id FROM pipelines WHERE id = ?", (body.pipeline_id,)).fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        s = conn.execute("SELECT id FROM pipeline_stages WHERE id = ? AND pipeline_id = ?", (body.stage_id, body.pipeline_id)).fetchone()
        if not s:
            raise HTTPException(status_code=404, detail="Stage not found in pipeline")

        contact_name, company_name, pipeline_name, stage_name = _resolve_names(
            conn, body.contact_id, body.company_id, body.pipeline_id, body.stage_id
        )
        conn.execute(
            """INSERT INTO opportunities
               (id, name, contact_id, contact_name, company_id, company_name,
                pipeline_id, pipeline_name, stage_id, stage_name,
                status, monetary_value, close_date, assigned_to, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                oid, body.name,
                body.contact_id, contact_name,
                body.company_id, company_name,
                body.pipeline_id, pipeline_name,
                body.stage_id, stage_name,
                body.status, body.monetary_value, body.close_date,
                body.assigned_to, body.notes, now, now,
            ),
        )
        row = conn.execute("SELECT * FROM opportunities WHERE id = ?", (oid,)).fetchone()
        return dict(row)


@router.get("/opportunities/{opp_id}")
def get_opportunity(opp_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        return dict(row)


@router.put("/opportunities/{opp_id}")
def update_opportunity(opp_id: str, body: OpportunityUpdate):
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        current = dict(existing)
        now = _now()

        sent = body.model_fields_set  # sent-but-blank means unlink; not sent means keep
        new_contact_id = body.contact_id if "contact_id" in sent else current.get("contact_id")
        new_company_id = body.company_id if "company_id" in sent else current.get("company_id")
        new_pipeline_id = body.pipeline_id if body.pipeline_id is not None else current.get("pipeline_id")
        new_stage_id = body.stage_id if body.stage_id is not None else current.get("stage_id")

        contact_name, company_name, pipeline_name, stage_name = _resolve_names(
            conn, new_contact_id, new_company_id, new_pipeline_id, new_stage_id
        )

        conn.execute(
            """UPDATE opportunities SET
               name = ?, contact_id = ?, contact_name = ?, company_id = ?, company_name = ?,
               pipeline_id = ?, pipeline_name = ?, stage_id = ?, stage_name = ?,
               status = ?, monetary_value = ?, close_date = ?, assigned_to = ?, notes = ?, updated_at = ?
               WHERE id = ?""",
            (
                body.name if body.name is not None else current["name"],
                new_contact_id, contact_name,
                new_company_id, company_name,
                new_pipeline_id, pipeline_name,
                new_stage_id, stage_name,
                body.status if body.status is not None
                else _status_for_stage(stage_name, current["status"]) if new_stage_id != current.get("stage_id")
                else current["status"],
                body.monetary_value if body.monetary_value is not None else current["monetary_value"],
                body.close_date if "close_date" in sent else current.get("close_date"),
                body.assigned_to if body.assigned_to is not None else current.get("assigned_to"),
                body.notes if body.notes is not None else current.get("notes"),
                now,
                opp_id,
            ),
        )
        if body.name is not None and body.name != current["name"]:
            for table in ("tasks", "activities"):
                conn.execute(f"UPDATE {table} SET opportunity_name = ? WHERE opportunity_id = ?", (body.name, opp_id))
        row = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        return dict(row)


@router.patch("/opportunities/{opp_id}/stage")
def move_opportunity_stage(opp_id: str, body: OpportunityStageUpdate):
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Opportunity not found")

        stage = conn.execute(
            "SELECT name FROM pipeline_stages WHERE id = ?", (body.stage_id,)
        ).fetchone()
        if not stage:
            raise HTTPException(status_code=404, detail="Stage not found")

        now = _now()
        conn.execute(
            "UPDATE opportunities SET stage_id = ?, stage_name = ?, status = ?, updated_at = ? WHERE id = ?",
            (body.stage_id, stage["name"], _status_for_stage(stage["name"], existing["status"]), now, opp_id),
        )
        row = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        return dict(row)


@router.delete("/opportunities/{opp_id}", status_code=204)
def delete_opportunity(opp_id: str):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        conn.execute("DELETE FROM opportunities WHERE id = ?", (opp_id,))
