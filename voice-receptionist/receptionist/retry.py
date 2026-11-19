"""Retry job: re-run every pending or failed call sync. Schedule it every 5 minutes.

    python -m receptionist.retry
"""
from __future__ import annotations

import json
import logging
import sys

from .alerts import Alerter
from .config import Settings
from .ghl import GHLClient
from .store import Store
from .sync import Syncer


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    store = Store(settings.db_path)
    results = Syncer(settings, GHLClient(settings), store, Alerter(store, settings.alert_webhook_url)).retry_pending()
    print(json.dumps(results, indent=2))
    return 0 if all(s == "done" for s in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
