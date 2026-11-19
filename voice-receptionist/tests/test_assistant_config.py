"""The rendered assistant must be internally consistent: every tool the prompt relies on exists, every
function tool is one the server handles, and the emergency transfer goes to a real-looking number."""
import json
from pathlib import Path

import pytest

from receptionist.assistant import ConfigError, render
from receptionist.tools import TOOLS

ROOT = Path(__file__).resolve().parents[1]
URL, CRED = "https://hooks.example.com/vapi/webhook", "cred_demo"


@pytest.fixture
def client():
    return json.loads((ROOT / "clients" / "tidewater-plumbing.json").read_text(encoding="utf-8"))


def test_renders_with_no_placeholders_left(client):
    out = json.dumps(render(client, URL, CRED))
    assert "{{" not in out and "Tidewater Plumbing" in out


def test_every_function_tool_has_a_server_handler(client):
    tools = render(client, URL, CRED)["model"]["tools"]
    functions = {t["function"]["name"] for t in tools if t["type"] == "function"}
    assert functions == set(TOOLS)
    assert all(t["server"]["url"] == URL and t["server"]["credentialId"] == CRED
               for t in tools if t["type"] == "function")


def test_emergency_transfer_is_wired_and_the_prompt_uses_it(client):
    a = render(client, URL, CRED)
    [transfer] = [t for t in a["model"]["tools"] if t["type"] == "transferCall"]
    assert transfer["destinations"][0]["number"] == "+17275550199"
    prompt = a["model"]["messages"][0]["content"]
    for tool in ("transferCall", "check_availability", "book_appointment"):
        assert tool in prompt
    assert "nine one one" in prompt


def test_server_receives_the_messages_the_backend_needs(client):
    assert set(render(client, URL, CRED)["serverMessages"]) >= {"end-of-call-report", "status-update", "tool-calls"}


@pytest.mark.parametrize("change, error", [
    ({"emergency_number": "727-555-0199"}, "E.164"),
    ({"faq": ""}, "missing: faq"),
])
def test_bad_client_files_are_refused(client, change, error):
    client.update(change)
    with pytest.raises(ConfigError, match=error):
        render(client, URL, CRED)


def test_refuses_http_and_raw_secrets(client):
    with pytest.raises(ConfigError, match="https"):
        render(client, "http://hooks.example.com", CRED)
    with pytest.raises(ConfigError, match="credential id"):
        render(client, URL, "sk_live_abc")
