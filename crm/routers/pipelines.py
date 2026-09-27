import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from ..db import get_db
from ..models import PipelineCreate, PipelineUpdate, StageCreate, StageUpdate, StageReorderItem

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_pipeline_with_stages(conn, pipeline_id: str) -> dict:
    p = conn.execute("SELECT * FROM pipelines WHERE id = ?", (pipeline_id,)).fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    stages = conn.execute(
        "SELECT * FROM pipeline_stages WHERE pipeline_id = ? ORDER BY position",
        (pipeline_id,),
    ).fetchall()
    return {**dict(p), "stages": [dict(s) for s in stages]}


# ── Pipelines ─────────────────────────────────────────────────────────────────

@router.get("/pipelines")
def list_pipelines():
    with get_db() as conn:
        pipelines = conn.execute("SELECT * FROM pipelines ORDER BY created_at").fetchall()
        result = []
        for p in pipelines:
            stages = conn.execute(
                "SELECT * FROM pipeline_stages WHERE pipeline_id = ? ORDER BY position",
                (p["id"],),
            ).fetchall()
            result.append({**dict(p), "stages": [dict(s) for s in stages]})
        return result


@router.post("/pipelines", status_code=201)
def create_pipeline(body: PipelineCreate):
    pid = str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO pipelines (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (pid, body.name, now, now),
        )
        return _get_pipeline_with_stages(conn, pid)


@router.get("/pipelines/{pipeline_id}")
def get_pipeline(pipeline_id: str):
    with get_db() as conn:
        return _get_pipeline_with_stages(conn, pipeline_id)


@router.put("/pipelines/{pipeline_id}")
def update_pipeline(pipeline_id: str, body: PipelineUpdate):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM pipelines WHERE id = ?", (pipeline_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        if body.name is not None:
            conn.execute(
                "UPDATE pipelines SET name = ?, updated_at = ? WHERE id = ?",
                (body.name, _now(), pipeline_id),
            )
            conn.execute(
                "UPDATE opportunities SET pipeline_name = ?, updated_at = ? WHERE pipeline_id = ?",
                (body.name, _now(), pipeline_id),
            )
        return _get_pipeline_with_stages(conn, pipeline_id)


@router.delete("/pipelines/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: str):
    with get_db() as conn:
        opp_count = conn.execute(
            "SELECT COUNT(*) FROM opportunities WHERE pipeline_id = ?", (pipeline_id,)
        ).fetchone()[0]
        if opp_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete: pipeline has {opp_count} linked opportunities",
            )
        conn.execute("DELETE FROM pipelines WHERE id = ?", (pipeline_id,))


# ── Stages ────────────────────────────────────────────────────────────────────

@router.post("/pipelines/{pipeline_id}/stages", status_code=201)
def add_stage(pipeline_id: str, body: StageCreate):
    with get_db() as conn:
        p = conn.execute("SELECT id FROM pipelines WHERE id = ?", (pipeline_id,)).fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if body.position is not None:
            position = body.position
        else:
            max_pos = conn.execute(
                "SELECT COALESCE(MAX(position), -1) FROM pipeline_stages WHERE pipeline_id = ?",
                (pipeline_id,),
            ).fetchone()[0]
            position = max_pos + 1

        sid = str(uuid.uuid4())
        now = _now()
        conn.execute(
            "INSERT INTO pipeline_stages (id, pipeline_id, name, position, color, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, pipeline_id, body.name, position, body.color, now, now),
        )
        return _get_pipeline_with_stages(conn, pipeline_id)


@router.put("/pipelines/{pipeline_id}/stages/{stage_id}")
def update_stage(pipeline_id: str, stage_id: str, body: StageUpdate):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM pipeline_stages WHERE id = ? AND pipeline_id = ?",
            (stage_id, pipeline_id),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Stage not found")

        now = _now()
        if body.name is not None:
            conn.execute(
                "UPDATE pipeline_stages SET name = ?, updated_at = ? WHERE id = ?",
                (body.name, now, stage_id),
            )
            conn.execute(
                "UPDATE opportunities SET stage_name = ?, updated_at = ? WHERE stage_id = ?",
                (body.name, now, stage_id),
            )
        if body.color is not None:
            conn.execute(
                "UPDATE pipeline_stages SET color = ?, updated_at = ? WHERE id = ?",
                (body.color, now, stage_id),
            )
        if body.position is not None:
            conn.execute(
                "UPDATE pipeline_stages SET position = ?, updated_at = ? WHERE id = ?",
                (body.position, now, stage_id),
            )
        return _get_pipeline_with_stages(conn, pipeline_id)


@router.delete("/pipelines/{pipeline_id}/stages/{stage_id}", status_code=204)
def delete_stage(pipeline_id: str, stage_id: str):
    with get_db() as conn:
        opp_count = conn.execute(
            "SELECT COUNT(*) FROM opportunities WHERE stage_id = ?", (stage_id,)
        ).fetchone()[0]
        if opp_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete: stage has {opp_count} linked opportunities",
            )
        conn.execute(
            "DELETE FROM pipeline_stages WHERE id = ? AND pipeline_id = ?",
            (stage_id, pipeline_id),
        )


@router.post("/pipelines/{pipeline_id}/stages/reorder")
def reorder_stages(pipeline_id: str, items: list[StageReorderItem]):
    with get_db() as conn:
        now = _now()
        for item in items:
            conn.execute(
                "UPDATE pipeline_stages SET position = ?, updated_at = ? WHERE id = ? AND pipeline_id = ?",
                (item.position, now, item.id, pipeline_id),
            )
        return _get_pipeline_with_stages(conn, pipeline_id)
