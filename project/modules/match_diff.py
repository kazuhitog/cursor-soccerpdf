from __future__ import annotations

import re
from typing import Any, Iterable

from .match_parser import Match
from .venue_resolver import normalize_location


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def make_match_key(match: Match) -> str:
    no_text = str(match.no)
    team_a = _normalize_text(match.teamA)
    team_b = _normalize_text(match.teamB)
    return f"{no_text}|{team_a}|{team_b}"


def _compare_value(field: str, match: Match) -> str:
    value = getattr(match, field, "")
    if field == "location":
        return normalize_location(str(value or ""))
    return _normalize_text(value)


def diff_matches(old_matches: Iterable[Match], new_matches: Iterable[Match]) -> dict[str, list[dict[str, Any]]]:
    old_map = {make_match_key(m): m for m in old_matches}
    new_map = {make_match_key(m): m for m in new_matches}

    old_keys = set(old_map.keys())
    new_keys = set(new_map.keys())

    compare_fields = ["date", "time", "location", "referee", "assistant"]

    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []

    for key in sorted(new_keys - old_keys):
        m = new_map[key]
        added.append(
            {
                "key": key,
                "match": m,
            }
        )

    for key in sorted(old_keys - new_keys):
        m = old_map[key]
        removed.append(
            {
                "key": key,
                "match": m,
            }
        )

    for key in sorted(old_keys & new_keys):
        old_match = old_map[key]
        new_match = new_map[key]

        changed_fields: list[str] = []
        for field in compare_fields:
            if _compare_value(field, old_match) != _compare_value(field, new_match):
                changed_fields.append(field)

        if changed_fields:
            changed.append(
                {
                    "key": key,
                    "old_match": old_match,
                    "new_match": new_match,
                    "changed_fields": changed_fields,
                }
            )

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def build_diff_rows(diff_result: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for item in diff_result["changed"]:
        old_match = item["old_match"]
        new_match = item["new_match"]
        changed_fields = ",".join(item["changed_fields"])

        rows.append(
            {
                "種別": "変更前",
                "試合キー": item["key"],
                "変更項目": changed_fields,
                "日付": old_match.date,
                "時間": old_match.time,
                "ホーム": old_match.teamA,
                "アウェー": old_match.teamB,
                "主審": old_match.referee,
                "副審": old_match.assistant,
                "会場": normalize_location(old_match.location),
                "_row_type": "before",
            }
        )
        rows.append(
            {
                "種別": "変更後",
                "試合キー": item["key"],
                "変更項目": changed_fields,
                "日付": new_match.date,
                "時間": new_match.time,
                "ホーム": new_match.teamA,
                "アウェー": new_match.teamB,
                "主審": new_match.referee,
                "副審": new_match.assistant,
                "会場": normalize_location(new_match.location),
                "_row_type": "after",
            }
        )

    for item in diff_result["added"]:
        m = item["match"]
        rows.append(
            {
                "種別": "追加",
                "試合キー": item["key"],
                "変更項目": "",
                "日付": m.date,
                "時間": m.time,
                "ホーム": m.teamA,
                "アウェー": m.teamB,
                "主審": m.referee,
                "副審": m.assistant,
                "会場": normalize_location(m.location),
                "_row_type": "added",
            }
        )

    for item in diff_result["removed"]:
        m = item["match"]
        rows.append(
            {
                "種別": "削除",
                "試合キー": item["key"],
                "変更項目": "",
                "日付": m.date,
                "時間": m.time,
                "ホーム": m.teamA,
                "アウェー": m.teamB,
                "主審": m.referee,
                "副審": m.assistant,
                "会場": normalize_location(m.location),
                "_row_type": "removed",
            }
        )

    return rows