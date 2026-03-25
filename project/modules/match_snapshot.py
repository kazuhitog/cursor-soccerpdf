from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, List

from .match_parser import Match

PROJECT_DIR = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = PROJECT_DIR / "data" / "snapshots"


def ensure_snapshot_dir() -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    return SNAPSHOT_DIR


def make_snapshot_filename(label: str | None = None) -> str:
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = (label or "snapshot").strip().replace(" ", "_")
    return f"{now}_{safe_label}.json"


def save_matches_snapshot(matches: List[Match], pdf_name: str, label: str | None = None) -> Path:
    snapshot_dir = ensure_snapshot_dir()
    file_name = make_snapshot_filename(label)
    path = snapshot_dir / file_name

    payload: dict[str, Any] = {
        "saved_at": datetime.now().isoformat(),
        "pdf_name": pdf_name,
        "label": label or "",
        "matches": [m.to_dict() for m in matches],
    }

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _match_from_dict(row: dict[str, Any]) -> Match:
    return Match(
        date=str(row.get("date", "")),
        age_group=row.get("age_group") or None,
        no=int(row.get("no", 0)),
        time=str(row.get("time", "")),
        teamA=str(row.get("teamA", "")),
        teamB=str(row.get("teamB", "")),
        referee=str(row.get("referee", "")),
        assistant=str(row.get("assistant", "")),
        location=str(row.get("location", "")),
    )


def load_matches_snapshot(path: str | Path) -> dict[str, Any]:
    snapshot_path = Path(path)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    matches = [_match_from_dict(row) for row in payload.get("matches", [])]

    return {
        "saved_at": payload.get("saved_at", ""),
        "pdf_name": payload.get("pdf_name", ""),
        "label": payload.get("label", ""),
        "matches": matches,
        "path": str(snapshot_path),
        "name": snapshot_path.name,
    }


def list_snapshots() -> list[dict[str, str]]:
    snapshot_dir = ensure_snapshot_dir()
    items: list[dict[str, str]] = []

    for path in sorted(snapshot_dir.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            items.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "saved_at": str(payload.get("saved_at", "")),
                    "pdf_name": str(payload.get("pdf_name", "")),
                    "label": str(payload.get("label", "")),
                }
            )
        except Exception:
            items.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "saved_at": "",
                    "pdf_name": "",
                    "label": "",
                }
            )
    return items