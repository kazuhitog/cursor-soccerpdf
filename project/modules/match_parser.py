from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Iterable


logger = logging.getLogger(__name__)

DATE_BLOCK_PATTERN = re.compile(r"(\d{1,2})月(\d{1,2})日")
HEADER_LINE_PATTERN = re.compile(r"開催日：\s*(\d+月\d+日)\s*会場：(.+)")
AGE_GROUP_PATTERN = re.compile(r"^\d{2}[A-Z]?$")
MATCH_HEAD_PATTERN = re.compile(r"^\d+\s+\d{1,2}:\d{2}")

# 例外チーム名（スペースを含むチーム名は事前に結合しておく）
SPECIAL_TEAM_NAMES = [
    "FC revoltijo",
    "fc ziarllo",
]


@dataclass
class Match:
    date: str  # YYYY-MM-DD
    age_group: str | None
    no: int
    time: str  # HH:MM
    teamA: str
    teamB: str
    referee: str
    assistant: str
    location: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "age_group": self.age_group or "",
            "no": self.no,
            "time": self.time,
            "teamA": self.teamA,
            "teamB": self.teamB,
            "referee": self.referee,
            "assistant": self.assistant,
            "location": self.location,
        }

    def start_end_datetimes(self) -> tuple[datetime, datetime]:
        start = datetime.strptime(f"{self.date} {self.time}", "%Y-%m-%d %H:%M")
        end = start + timedelta(minutes=120)
        return start, end


def _normalize_date_from_block(text: str, year: int | None = None) -> str | None:
    """
    「4月5日」のような表記を YYYY-MM-DD に変換。
    year が指定されない場合は今年を利用。
    """
    m = DATE_BLOCK_PATTERN.search(text)
    if not m:
        return None

    month = int(m.group(1))
    day = int(m.group(2))
    if year is None:
        year = datetime.today().year
    dt = datetime(year, month, day)
    return dt.strftime("%Y-%m-%d")


def _log_parse_error(line: str) -> None:
    """
    試合行解析エラーをログファイルに保存する。
    """
    try:
        logs_dir = Path(__file__).resolve().parents[1] / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / "parser_error.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"試合行解析エラー: {line}\n")
    except Exception:  # noqa: BLE001
        logger.exception("試合行解析エラーのログ出力に失敗しました")


def _apply_special_team_join(line: str) -> str:
    """
    例外チーム名を一時的に「スペースなし表記」に変換する。
    例: 'FC revoltijo' -> 'FC_revoltijo'
    """
    for name in SPECIAL_TEAM_NAMES:
        joined = name.replace(" ", "_")
        line = line.replace(name, joined)
    return line


def _restore_special_team_name(name: str) -> str:
    """
    結合表記を元のスペースあり表記に戻す。
    例: 'FC_revoltijo' -> 'FC revoltijo'
    """
    return name.replace("_", " ")


def parse_matches_from_lines(lines: Iterable[str], year: int | None = None) -> List[Match]:
    """
    PDF から取得した行リストをもとに、日付ブロック＋試合行を解析して Match リストを返す。
    """
    # 行列化しておく（年検出などで複数回走査するため）
    line_list = list(lines)

    # 年が指定されていない場合はタイトルから自動検出
    if year is None:
        detected_year: int | None = None
        for raw in line_list:
            m_year = re.search(r"(\d{4})年", raw)
            if m_year:
                try:
                    detected_year = int(m_year.group(1))
                    break
                except Exception:  # noqa: BLE001
                    continue
        year = detected_year

    current_date: str | None = None
    current_location: str | None = None
    current_age_group: str | None = None
    matches: List[Match] = []

    for raw in line_list:
        original = raw.strip()
        if not original:
            continue

        # 開催日・会場ヘッダー行の検出
        m_header = HEADER_LINE_PATTERN.search(original)
        if m_header:
            date_text = m_header.group(1)
            loc_text = m_header.group(2).strip()
            norm_date = _normalize_date_from_block(date_text, year=year)
            if norm_date:
                current_date = norm_date
            current_location = loc_text
            continue

        # 日付ブロックの更新
        new_date = _normalize_date_from_block(original, year=year)
        if new_date:
            current_date = new_date
            continue

        # 例外チーム名を結合した上でトークン化
        line = _apply_special_team_join(original)

        # 年代のみ行（例: "60", "50A", "22: 40A"）
        tokens = line.replace("：", ":").split()
        if tokens:
            last_token = tokens[-1]
            if AGE_GROUP_PATTERN.match(last_token):
                current_age_group = last_token
                continue

        # 試合行の解析
        if not current_date:
            continue
        if not MATCH_HEAD_PATTERN.match(line):
            # 年代付き試合行かもしれないので、先頭トークンをずらして再チェック
            if not tokens or len(tokens) < 3:
                continue
            if not (AGE_GROUP_PATTERN.match(tokens[0]) and MATCH_HEAD_PATTERN.match(" ".join(tokens[1:3]))):
                continue

        try:
            age_group: str | None
            no: int
            time_str: str

            # 年代が先頭に付くケースかどうか
            if tokens and AGE_GROUP_PATTERN.match(tokens[0]):
                age_group = tokens[0]
                no = int(tokens[1])
                time_str = tokens[2]
                base_idx = 3
            else:
                age_group = current_age_group
                no = int(tokens[0])
                time_str = tokens[1]
                base_idx = 2

            # 仕様に合わせて単純なトークン分割で解析
            # No 時間 H × A 主審 副審
            #   base_idx: H
            home = _restore_special_team_name(tokens[base_idx])
            away = _restore_special_team_name(tokens[base_idx + 2])
            referee = _restore_special_team_name(tokens[base_idx + 3]) if len(tokens) > base_idx + 3 else ""
            assistant = _restore_special_team_name(tokens[base_idx + 4]) if len(tokens) > base_idx + 4 else ""

            match = Match(
                date=current_date,
                age_group=age_group,
                no=no,
                time=time_str,
                teamA=home,
                teamB=away,
                referee=referee,
                assistant=assistant,
                location=current_location or "",
            )
            matches.append(match)
        except Exception:  # noqa: BLE001
            _log_parse_error(line)
            continue

    return matches


def filter_matches_by_team(matches: Iterable[Match], team_name: str) -> List[Match]:
    """
    team_name を含む試合だけを抽出。
    """
    team_name = (team_name or "").strip()
    if not team_name:
        return list(matches)

    result: List[Match] = []
    for m in matches:
        if team_name in m.teamA or team_name in m.teamB:
            result.append(m)
    return result


__all__ = ["Match", "parse_matches_from_lines", "filter_matches_by_team"]

