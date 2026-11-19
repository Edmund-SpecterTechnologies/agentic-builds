import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fake_ghl import FakeGHL  # noqa: E402
from receptionist.alerts import Alerter  # noqa: E402
from receptionist.config import Settings  # noqa: E402
from receptionist.ghl import GHLClient  # noqa: E402
from receptionist.server import create_app  # noqa: E402
from receptionist.store import Store  # noqa: E402

SECRET = "test-shared-secret"
CALLER = "+17275550142"
# Monday 2026-11-23, 9:00 AM Eastern
NOW = datetime(2026, 11, 23, 14, 0, tzinfo=timezone.utc)
SLOTS = [
    "2026-11-23T10:00:00-05:00",
    "2026-11-23T11:00:00-05:00",
    "2026-11-24T09:00:00-05:00",
    "2026-11-24T13:00:00-05:00",
]


def load_fixture(name: str) -> dict:
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


@pytest.fixture
def settings(tmp_path):
    return Settings(
        vapi_secret=SECRET, ghl_token="ghl-test-token", ghl_location_id="loc_demo",
        ghl_calendar_id="cal_demo", ghl_pipeline_id="pipe_demo", stage_new_lead="stage_new",
        stage_booked="stage_booked", stage_emergency="stage_emergency", owner_contact_id="ct_owner",
        db_path=str(tmp_path / "ledger.db"), max_sync_attempts=3,
    )


class Harness:
    def __init__(self, settings):
        self.settings = settings
        self.ghl_fake = FakeGHL(settings.ghl_token, SLOTS)
        self.store = Store(settings.db_path)
        self.alerts = Alerter(self.store)
        self.ghl = GHLClient(settings, transport=self.ghl_fake.transport(), sleep=lambda s: None)
        self.app = create_app(settings, ghl=self.ghl, store=self.store, alerts=self.alerts, now=lambda: NOW)
        self.client = TestClient(self.app)
        self.syncer = self.app.state.syncer

    def post(self, body: dict, secret: str = SECRET):
        return self.client.post("/vapi/webhook", json=body, headers={"Authorization": f"Bearer {secret}"})

    def tool(self, name: str, args: dict, call_id: str = "call_demo_0001", tool_call_id: str = "tc_1"):
        body = load_fixture("tool-calls.json")
        body["message"]["call"]["id"] = call_id
        body["message"]["toolCallList"] = [
            {"id": tool_call_id, "type": "function", "function": {"name": name, "arguments": args}}]
        r = self.post(body)
        assert r.status_code == 200, "Vapi ignores any non-200 tool reply"
        return r.json()["results"][0]

    def report(self, call_id: str = "call_demo_0001", **overrides):
        body = copy.deepcopy(load_fixture("end-of-call-report.json"))
        body["message"]["call"]["id"] = call_id
        body["message"].update(overrides)
        return self.post(body)


@pytest.fixture
def h(settings):
    return Harness(settings)
