from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def load_seen_ids(path: str | Path) -> set[str]:
    store_path = Path(path)
    if not store_path.exists():
        return set()

    try:
        data = json.loads(store_path.read_text(encoding="utf-8"))
        return set(data.get("seen_ids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen_ids(path: str | Path, seen_ids: set[str]) -> None:
    store_path = Path(path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seen_ids": sorted(seen_ids),
        "last_run": datetime.now(timezone.utc).isoformat(),
    }
    store_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
