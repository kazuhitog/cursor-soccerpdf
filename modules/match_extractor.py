from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd


logger = logging.getLogger(__name__)


@dataclass
class Match:
    date: str
    time: str
    location: str
    home: str
    away: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "time": self.time,
            "location": self.location,
            "home": self.home,
            "away": self.away,
        }

    def start_end_datetimes(self) -> tuple[datetime, datetime]:
        """
        YYYY-MM-DD, HH:MM を datetime に変換し、固定 120 分試合として終了時間も返す。
        """
        start = datetime.strptime(f"{self.date} {self.time}", "%Y-%m-%d %H:%M")
        end = start + timedelta(minutes=120)
        return start, end


def load_team_name(config_path: Path) -> str:
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return str(data.get("team_name", "")).strip()


def split_match_card(card: str) -> tuple[str, str] | tuple[None, None]:
    """
    「Aチーム vs Bチーム」形式の文字列から (home, away) を抽出。
    区切り文字は「vs」「VS」「ｖｓ」「ＶＳ」「－」「-」などを緩くサポート。
    """
    if not card:
        return None, None

    separators = ["vs", "VS", "ｖｓ", "ＶＳ", "-", "－", "ー"]
    for sep in separators:
        if sep in card:
            parts = [p.strip() for p in card.split(sep, maxsplit=1)]
            if len(parts) == 2:
                return parts[0], parts[1]
    return None, None


def normalize_date(date_str: str, year: int | None = None) -> str | None:
    """
    「4/3」「2026/4/3」などを YYYY-MM-DD 形式に正規化。
    年が含まれない場合は引数 year を使用（指定が無ければ今年）。
    """
    date_str = str(date_str).strip()
    if not date_str:
        return None

    try:
        if "年" in date_str and "月" in date_str and "日" in date_str:
            # 例: 2026年4月3日
            date_str = (
                date_str.replace("年", "/")
                .replace("月", "/")
                .replace("日", "")
            )

        if date_str.count("/") == 2:
            dt = datetime.strptime(date_str, "%Y/%m/%d")
        else:
            # 年がない場合
            if year is None:
                year = datetime.today().year
            dt = datetime.strptime(f"{year}/{date_str}", "%Y/%m/%d")
        return dt.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        logger.warning("日付形式エラー: %s", date_str)
        return None


def normalize_time(time_str: str) -> str | None:
    """
    「19:00」「19時00分」「7:00 PM」などを HH:MM 24h 形式に正規化。
    """
    time_str = str(time_str).strip()
    if not time_str:
        return None

    # 日本語表記の簡易対応
    time_str = (
        time_str.replace("時", ":")
        .replace("分", "")
        .replace("午前", "AM")
        .replace("午後", "PM")
    )

    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p"):
        try:
            t = datetime.strptime(time_str, fmt)
            return t.strftime("%H:%M")
        except Exception:  # noqa: BLE001
            continue

    logger.warning("時間形式エラー: %s", time_str)
    return None


def extract_team_matches(df: pd.DataFrame, team_name: str, year: int | None = None) -> List[Match]:
    """
    DataFrame[date, time, place, match] から、team_name を含む試合のみを
    Match リストとして返す。
    """
    team_name = str(team_name).strip()
    if not team_name:
        return []

    matches: List[Match] = []
    for _, row in df.iterrows():
        card = str(row.get("match", "")).strip()
        if team_name not in card:
            continue

        date_norm = normalize_date(row.get("date", ""), year=year)
        time_norm = normalize_time(row.get("time", ""))
        if not date_norm or not time_norm:
            # 日付・時間解析エラー
            logger.warning("日付形式エラー or 時間形式エラー（スキップ）: %s %s", row.get("date"), row.get("time"))
            continue

        home, away = split_match_card(card)
        if not home or not away:
            home = card
            away = ""

        match = Match(
            date=date_norm,
            time=time_norm,
            location=str(row.get("place", "")).strip(),
            home=home,
            away=away,
        )
        matches.append(match)

    return matches


__all__ = ["Match", "load_team_name", "extract_team_matches"]

