from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Iterable, Set


logger = logging.getLogger(__name__)

DATE_BLOCK_PATTERN = re.compile(r"(\d{1,2})月(\d{1,2})日")
HEADER_LINE_PATTERN = re.compile(r"開催日：\s*(\d+月\d+日)\s*会場：(.+)")
AGE_GROUP_PATTERN = re.compile(r"^\d{2}[A-Z]?$")
MATCH_HEAD_PATTERN = re.compile(r"^\d+\s+\d{1,2}:\d{2}")
AGE_GROUP_TOKEN_PATTERN = re.compile(r"\b(?:40A|40B|40C|50A|50B|60|70)\b")
LOCATION_ONLY_PATTERN = re.compile(r"会場：(.+)")


# 例外チーム名（スペースを含むチーム名）。ファイルが無い場合のデフォルト。
DEFAULT_SPECIAL_TEAM_NAMES = [
    "FC revoltijo",
    "fc ziarllo",
    "Regalis F.C",
]

# モジュールの親 = project/
PROJECT_DIR = Path(__file__).resolve().parents[1]
SPECIAL_TEAM_NAMES_FILE = PROJECT_DIR / "data" / "special_team_names.txt"


def get_special_team_names_path() -> Path:
    """特殊チーム名一覧ファイルのパスを返す。"""
    return SPECIAL_TEAM_NAMES_FILE


def load_special_team_names() -> List[str]:
    """
    特殊チーム名をファイルから読み込む。
    ファイルが無いか空の場合は DEFAULT_SPECIAL_TEAM_NAMES を返す。
    """
    if not SPECIAL_TEAM_NAMES_FILE.exists():
        return list(DEFAULT_SPECIAL_TEAM_NAMES)
    lines = SPECIAL_TEAM_NAMES_FILE.read_text(encoding="utf-8").strip().splitlines()
    names = [s.strip() for s in lines if s.strip()]
    return names if names else list(DEFAULT_SPECIAL_TEAM_NAMES)


def save_special_team_names(names: List[str]) -> None:
    """特殊チーム名一覧をファイルに保存する。"""
    SPECIAL_TEAM_NAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    SPECIAL_TEAM_NAMES_FILE.write_text("\n".join(names), encoding="utf-8")


def _apply_special_team_join(line: str, names: List[str] | None = None) -> str:
    """
    例外チーム名を一時的に「スペースなし表記」に変換する。
    names が None の場合は load_special_team_names() を使用。
    """
    if names is None:
        names = load_special_team_names()
    for name in names:
        joined = name.replace(" ", "_")
        line = line.replace(name, joined)
    return line


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


def _restore_special_team_name(name: str) -> str:
    """
    結合表記を元のスペースあり表記に戻す。
    例: 'FC_revoltijo' -> 'FC revoltijo'
    """
    return name.replace("_", " ")


def parse_matches_from_lines(lines: Iterable[str], year: int | None = None) -> List[Match]:
    """
    PDF から取得した行リストをもとに、日付ブロック＋試合行を解析して Match リストを返す。
    特殊チーム名は data/special_team_names.txt から読み込む。
    """
    special_names = load_special_team_names()
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
    # current_location: str | None = None
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
            # loc_text = m_header.group(2).strip()
            norm_date = _normalize_date_from_block(date_text, year=year)
            if norm_date:
                current_date = norm_date
            continue

        # 日付ブロックの更新
        new_date = _normalize_date_from_block(original, year=year)
        if new_date:
            current_date = new_date
            continue

        # 例外チーム名を結合した上でトークン化
        line = _apply_special_team_join(original, special_names)

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
                location="",
            )
            matches.append(match)
        except Exception:  # noqa: BLE001
            _log_parse_error(line)
            continue

    return matches

EXCLUDED_TEAM_NAMES = {
    "1位",
    "2位",
    "3位",
    "4位",
    "5位",
    "6位",
    "7位",
    "8位",
    "1試合目勝者",
    "40A1位",
    "40B1位",
    "40C",
    "40C1位",
    "50A",
    "50A1位",
    "50B1位",
    "70A",
    "70B",
    "×",
}

def normalize_team_candidate(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" 　-–—/｜|:：()[]{}【】「」")
    return s



# チーム名一覧取得関数
def extract_team_names(matches: Iterable[Match]) -> List[str]:
    """
    Match一覧からチーム名を重複なしで抽出して返す。
    デフォルトで「ハマーズ」を先頭候補に含める。
    除外リストに一致する文字列は候補に入れない。
    """
    team_set: set[str] = set()

    for m in matches:
        if m.teamA and m.teamA.strip():
            team_a = m.teamA.strip()
            if team_a not in EXCLUDED_TEAM_NAMES:
                team_set.add(team_a)

        if m.teamB and m.teamB.strip():
            team_b = m.teamB.strip()
            if team_b not in EXCLUDED_TEAM_NAMES:
                team_set.add(team_b)

    teams = sorted(team_set)

    # デフォルト候補としてハマーズを先頭に置く
    if "ハマーズ" in teams:
        teams.remove("ハマーズ")
    teams.insert(0, "ハマーズ")

    return teams

def filter_matches_by_team(matches: Iterable[Match], team_name: str) -> List[Match]:
    """
    指定した team_name と完全一致する試合だけを抽出。
    前後空白や連続スペースの揺れだけ吸収する。
    """
    target = normalize_team_candidate(team_name)
    if not target:
        return list(matches)

    result: List[Match] = []
    for m in matches:
        team_a = normalize_team_candidate(m.teamA)
        team_b = normalize_team_candidate(m.teamB)

        if target == team_a or target == team_b:
            result.append(m)
    return result

def filter_matches_by_teams(matches: Iterable[Match], team_names: Iterable[str]) -> List[Match]:
    """
    指定した team_names のいずれかに完全一致する試合だけを抽出。
    """
    targets = {
        normalize_team_candidate(name)
        for name in team_names
        if normalize_team_candidate(name)
    }

    if not targets:
        return list(matches)

    result: List[Match] = []
    for m in matches:
        team_a = normalize_team_candidate(m.teamA)
        team_b = normalize_team_candidate(m.teamB)

        if team_a in targets or team_b in targets:
            result.append(m)

    return result


def parse_matches_from_pages(pages: Iterable[Iterable[str]], year: int | None = None) -> List[Match]:
    all_matches: List[Match] = []

    if year is None:
        detected_year: int | None = None
        for page_lines in pages:
            for raw in page_lines:
                m_year = re.search(r"(\d{4})年", raw)
                if m_year:
                    try:
                        detected_year = int(m_year.group(1))
                        break
                    except Exception:
                        continue
            if detected_year is not None:
                break
        year = detected_year

    for page_lines in pages:
        page_line_list = list(page_lines)

        page_matches = parse_matches_from_lines(page_line_list, year=year)
        location_map = _extract_page_date_age_location_map(page_line_list, year=year)
        _assign_locations_to_matches(page_matches, location_map)

        all_matches.extend(page_matches)

    return all_matches

def _extract_page_date_age_location_map(
    page_lines: Iterable[str],
    year: int | None = None,
) -> dict[tuple[str, str], str]:
    location_map: dict[tuple[str, str], str] = {}
    current_date: str | None = None
    pending_age_groups: list[str] = []

    for raw in page_lines:
        original = raw.strip()
        if not original:
            continue

        # 日付を更新
        new_date = _normalize_date_from_block(original, year=year)
        if new_date:
            current_date = new_date

        # 行中から年代を全部拾う
        found_age_groups = AGE_GROUP_TOKEN_PATTERN.findall(original)
        for age in found_age_groups:
            if age not in pending_age_groups:
                pending_age_groups.append(age)

        location: str | None = None

        # 「開催日： 4月25日 会場：○○」形式
        m_header = HEADER_LINE_PATTERN.search(original)
        if m_header:
            date_text = m_header.group(1)
            loc_text = m_header.group(2).strip()
            norm_date = _normalize_date_from_block(date_text, year=year)
            if norm_date:
                current_date = norm_date
            location = loc_text
        else:
            # 「会場：○○」だけの行
            m_loc = LOCATION_ONLY_PATTERN.search(original)
            if m_loc:
                location = m_loc.group(1).strip()

        # 直前に見つけた年代群へ会場を割り当てる
        if location and current_date and pending_age_groups:
            for age in pending_age_groups:
                location_map[(current_date, age)] = location
            pending_age_groups = []

    return location_map

def _assign_locations_to_matches(
    matches: List[Match],
    location_map: dict[tuple[str, str], str],
) -> None:
    for m in matches:
        if not m.age_group:
            continue

        key = (m.date, m.age_group)
        if key in location_map:
            m.location = location_map[key]



__all__ = [
    "Match",
    "parse_matches_from_lines",
    "parse_matches_from_pages",
    "extract_team_names",
    "filter_matches_by_team",
    "filter_matches_by_teams",
    "load_special_team_names",
    "save_special_team_names",
    "get_special_team_names_path",
]