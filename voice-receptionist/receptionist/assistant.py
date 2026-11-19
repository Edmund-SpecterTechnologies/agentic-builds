"""Render one client's Vapi assistant from the shared template and that client's values file.

One template for every client is what keeps monthly builds consistent: a fix to the emergency rule or the
booking tools lands in every client's next render, and a client file only holds facts about that business.
Rendering refuses to produce a config with an unfilled placeholder, a non-https server URL, an emergency
number that is not E.164, or a secret pasted inline.

    python -m receptionist.assistant clients/tidewater-plumbing.json \
        --server-url https://hooks.example.com/vapi/webhook --credential-id cred_123 > tidewater.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_]+)\s*\}\}")
E164 = re.compile(r"^\+[1-9]\d{7,14}$")
REQUIRED = ("business_name", "trade", "service_area", "hours", "timezone", "emergency_number",
            "emergency_signs", "services", "faq")


class ConfigError(ValueError):
    pass


def _fill(text: str, values: dict) -> str:
    return PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)


def render(client: dict, server_url: str, credential_id: str) -> dict:
    missing = [k for k in REQUIRED if not str(client.get(k, "")).strip()]
    if missing:
        raise ConfigError(f"client file is missing: {', '.join(missing)}")
    if not E164.match(client["emergency_number"]):
        raise ConfigError(f"emergency_number must be E.164 (+15551234567), got {client['emergency_number']!r}")
    if not server_url.startswith("https://"):
        raise ConfigError("server URL must be https")
    if not credential_id.startswith("cred"):
        raise ConfigError("pass the Vapi credential id (cred_...), never the secret itself")

    prompt = _fill((ROOT / "assistant" / "system-prompt.md").read_text(encoding="utf-8"), client)
    values = dict(client, SYSTEM_PROMPT=prompt, SERVER_URL=server_url, CREDENTIAL_ID=credential_id)
    template = json.loads((ROOT / "assistant" / "template.json").read_text(encoding="utf-8"))

    def walk(node):
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return _fill(node, values) if isinstance(node, str) else node

    out = walk(template)
    leftover = sorted(set(PLACEHOLDER.findall(json.dumps(out))))
    if leftover:
        raise ConfigError(f"unfilled placeholders: {', '.join(leftover)}")
    if re.search(r'"(secret|apiKey|token)"\s*:', json.dumps(out), re.I):
        raise ConfigError("rendered config contains an inline secret field")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render a client's Vapi assistant config")
    p.add_argument("client_file")
    p.add_argument("--server-url", required=True)
    p.add_argument("--credential-id", required=True)
    a = p.parse_args(argv)
    client = json.loads(Path(a.client_file).read_text(encoding="utf-8"))
    try:
        print(json.dumps(render(client, a.server_url, a.credential_id), indent=2))
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
