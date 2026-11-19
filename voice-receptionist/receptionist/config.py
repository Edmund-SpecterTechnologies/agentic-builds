"""Per-client settings. One deployment (or one .env) per client sub-account."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    vapi_secret: str            # shared secret Vapi sends (Bearer or X-Vapi-Secret credential)
    ghl_token: str              # sub-account Private Integration token
    ghl_location_id: str
    ghl_calendar_id: str
    ghl_pipeline_id: str
    stage_new_lead: str         # pipeline stage ids, one per call outcome
    stage_booked: str
    stage_emergency: str
    owner_contact_id: str       # GHL contact that receives the owner's post-call text
    timezone: str = "America/New_York"
    appointment_minutes: int = 60
    ghl_base_url: str = "https://services.leadconnectorhq.com"
    ghl_version: str = "2021-07-28"
    db_path: str = "receptionist.db"
    alert_webhook_url: str = ""  # Slack-style incoming webhook; empty = log and store only
    max_sync_attempts: int = 5   # after this many failed passes an event is dead-lettered

    def stage_for(self, outcome: str) -> str:
        return {"emergency": self.stage_emergency, "booked": self.stage_booked}.get(outcome, self.stage_new_lead)

    @classmethod
    def from_env(cls) -> "Settings":
        try:  # a local .env, if present; real environment variables win
            from dotenv import find_dotenv, load_dotenv
            # usecwd: search from where the command runs, not from this package's folder
            load_dotenv(find_dotenv(usecwd=True), override=False)
        except ImportError:
            pass

        def need(name: str) -> str:
            value = os.environ.get(name, "").strip()
            if not value:
                raise RuntimeError(f"{name} is not set")
            return value

        return cls(
            vapi_secret=need("VAPI_SERVER_SECRET"),
            ghl_token=need("GHL_TOKEN"),
            ghl_location_id=need("GHL_LOCATION_ID"),
            ghl_calendar_id=need("GHL_CALENDAR_ID"),
            ghl_pipeline_id=need("GHL_PIPELINE_ID"),
            stage_new_lead=need("GHL_STAGE_NEW_LEAD"),
            stage_booked=need("GHL_STAGE_BOOKED"),
            stage_emergency=need("GHL_STAGE_EMERGENCY"),
            owner_contact_id=need("GHL_OWNER_CONTACT_ID"),
            timezone=os.environ.get("CLIENT_TIMEZONE", "America/New_York"),
            appointment_minutes=int(os.environ.get("APPOINTMENT_MINUTES", "60")),
            ghl_version=os.environ.get("GHL_API_VERSION", "2021-07-28"),
            db_path=os.environ.get("RECEPTIONIST_DB", "receptionist.db"),
            alert_webhook_url=os.environ.get("ALERT_WEBHOOK_URL", ""),
        )
