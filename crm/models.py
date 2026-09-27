from typing import Literal, Optional
from pydantic import BaseModel as _PydanticModel, model_validator


class BaseModel(_PydanticModel):
    """Shared base: a blank reference or date means "not set".

    The forms send "" for an unselected company, contact, deal, or date. Stored
    as-is, "" is treated as a real id and fails the foreign-key check, so
    creating a contact with no company used to return a 500.
    """

    @model_validator(mode="before")
    @classmethod
    def _blank_refs_to_none(cls, data):
        if isinstance(data, dict):
            return {k: (None if v == "" and (k.endswith("_id") or k.endswith("_date")) else v)
                    for k, v in data.items()}
        return data


# Closed sets of values. The page styles and filters on these, so the API refuses anything else.
ContactStatus = Literal["active", "inactive"]
DealStatus = Literal["open", "won", "lost"]
TaskStatus = Literal["open", "done"]
ActivityType = Literal["call", "email", "sms", "note"]
SavedViewEntity = Literal["contacts", "opportunities", "tasks"]

# ── Contacts ─────────────────────────────────────────────────────────────────

class ContactCreate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company_id: Optional[str] = None
    tags: list[str] = []
    source: Optional[str] = None
    status: ContactStatus = "active"
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company_id: Optional[str] = None
    tags: Optional[list[str]] = None
    source: Optional[str] = None
    status: Optional[ContactStatus] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class ContactResponse(BaseModel):
    id: str
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    company_id: Optional[str]
    company_name: Optional[str]
    tags: list[str]
    source: Optional[str]
    status: str
    assigned_to: Optional[str]
    notes: Optional[str]
    created_at: str
    updated_at: str


# ── Companies ─────────────────────────────────────────────────────────────────

class CompanyCreate(BaseModel):
    name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class CompanyResponse(BaseModel):
    id: str
    name: str
    industry: Optional[str]
    website: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    notes: Optional[str]
    created_at: str
    updated_at: str


# ── Pipelines & Stages ────────────────────────────────────────────────────────

class PipelineCreate(BaseModel):
    name: str


class PipelineUpdate(BaseModel):
    name: Optional[str] = None


class StageCreate(BaseModel):
    name: str
    color: str = "#6B7280"
    position: Optional[int] = None


class StageUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None


class StageResponse(BaseModel):
    id: str
    pipeline_id: str
    name: str
    position: int
    color: str
    created_at: str
    updated_at: str


class PipelineResponse(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str
    stages: list[StageResponse] = []


class StageReorderItem(BaseModel):
    id: str
    position: int


# ── Opportunities ─────────────────────────────────────────────────────────────

class OpportunityCreate(BaseModel):
    name: str
    contact_id: Optional[str] = None
    company_id: Optional[str] = None
    pipeline_id: str
    stage_id: str
    status: DealStatus = "open"
    monetary_value: float = 0
    close_date: Optional[str] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class OpportunityUpdate(BaseModel):
    name: Optional[str] = None
    contact_id: Optional[str] = None
    company_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    stage_id: Optional[str] = None
    status: Optional[DealStatus] = None
    monetary_value: Optional[float] = None
    close_date: Optional[str] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class OpportunityStageUpdate(BaseModel):
    stage_id: str


class OpportunityResponse(BaseModel):
    id: str
    name: str
    contact_id: Optional[str]
    contact_name: Optional[str]
    company_id: Optional[str]
    company_name: Optional[str]
    pipeline_id: str
    pipeline_name: Optional[str]
    stage_id: str
    stage_name: Optional[str]
    status: str
    monetary_value: float
    close_date: Optional[str]
    assigned_to: Optional[str]
    notes: Optional[str]
    created_at: str
    updated_at: str


# ── Activities ────────────────────────────────────────────────────────────────

class ActivityCreate(BaseModel):
    type: ActivityType
    body: Optional[str] = None
    contact_id: Optional[str] = None
    opportunity_id: Optional[str] = None


class ActivityResponse(BaseModel):
    id: str
    type: str
    body: Optional[str]
    contact_id: Optional[str]
    contact_name: Optional[str]
    opportunity_id: Optional[str]
    opportunity_name: Optional[str]
    created_at: str


# ── Tasks ─────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    due_date: Optional[str] = None
    contact_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[TaskStatus] = None
    contact_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class TaskResponse(BaseModel):
    id: str
    title: str
    due_date: Optional[str]
    status: str
    contact_id: Optional[str]
    contact_name: Optional[str]
    opportunity_id: Optional[str]
    opportunity_name: Optional[str]
    assigned_to: Optional[str]
    notes: Optional[str]
    created_at: str
    updated_at: str


# ── Saved Views ───────────────────────────────────────────────────────────────

class SavedViewCreate(BaseModel):
    name: str
    entity: SavedViewEntity
    filters: dict = {}


class SavedViewResponse(BaseModel):
    id: str
    name: str
    entity: str
    filters: dict
    created_at: str
