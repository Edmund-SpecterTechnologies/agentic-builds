import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from ..db import get_db
from ..models import SavedViewCreate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/saved-views")
def list_saved_views(entity: str = Query(default="")):
    with get_db() as conn:
        if entity:
            rows = conn.execute(
                "SELECT * FROM saved_views WHERE entity = ? ORDER BY created_at ASC",
                (entity,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM saved_views ORDER BY entity, created_at ASC"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["filters"] = json.loads(d.get("filters") or "{}")
            except Exception:
                d["filters"] = {}
            result.append(d)
        return result


@router.post("/saved-views", status_code=201)
def create_saved_view(body: SavedViewCreate):
    vid = str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO saved_views (id, name, entity, filters, created_at) VALUES (?, ?, ?, ?, ?)",
            (vid, body.name, body.entity, json.dumps(body.filters), now),
        )
        row = conn.execute("SELECT * FROM saved_views WHERE id = ?", (vid,)).fetchone()
        d = dict(row)
        try:
            d["filters"] = json.loads(d.get("filters") or "{}")
        except Exception:
            d["filters"] = {}
        return d


@router.delete("/saved-views/{view_id}", status_code=204)
def delete_saved_view(view_id: str):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM saved_views WHERE id = ?", (view_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Saved view not found")
        conn.execute("DELETE FROM saved_views WHERE id = ?", (view_id,))
