"""The server URL's front door: authentication, malformed bodies, and message routing."""
from conftest import load_fixture


def test_rejects_missing_and_wrong_secret(h):
    body = load_fixture("tool-calls.json")
    assert h.client.post("/vapi/webhook", json=body).status_code == 401
    assert h.post(body, secret="wrong").status_code == 401
    assert h.ghl_fake.calls == [], "an unauthenticated request must not reach GHL"


def test_accepts_legacy_x_vapi_secret_header(h):
    r = h.client.post("/vapi/webhook", json=load_fixture("tool-calls.json"),
                      headers={"X-Vapi-Secret": "test-shared-secret"})
    assert r.status_code == 200


def test_malformed_bodies_are_400_not_500(h):
    auth = {"Authorization": "Bearer test-shared-secret", "Content-Type": "application/json"}
    assert h.client.post("/vapi/webhook", content=b"not json", headers=auth).status_code == 400
    assert h.client.post("/vapi/webhook", json=["a"], headers=auth).status_code == 400
    assert h.client.post("/vapi/webhook", json={"nope": 1}, headers=auth).status_code == 400


def test_unknown_message_types_are_acknowledged(h):
    r = h.post({"message": {"type": "speech-update", "call": {"id": "call_x"}}})
    assert r.status_code == 200 and r.json() == {"ignored": "speech-update"}


def test_report_without_call_id_alerts_instead_of_vanishing(h):
    r = h.post({"message": {"type": "end-of-call-report", "call": {}}})
    assert r.status_code == 200
    assert any("no call id" in a["message"] for a in h.store.alerts())
