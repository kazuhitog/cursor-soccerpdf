from __future__ import annotations

from urllib.parse import urlencode, quote

from .match_parser import Match


def build_google_calendar_url(match: Match) -> str:
    """
    仕様に基づき Google カレンダー追加用 URL を生成する。
    - タイトル: "{home} vs {away}"
    - 開始: match.date + match.time
    - 終了: 開始 + 120分
    - 詳細: 年代/試合番号/主審/副審 を改行付きで記載
    """
    start_dt, end_dt = match.start_end_datetimes()

    fmt = "%Y%m%dT%H%M%S"
    dates = f"{start_dt.strftime(fmt)}/{end_dt.strftime(fmt)}"

    # イベントタイトル（対戦カード）
    title = f"{match.teamA} vs {match.teamB}"

    # 詳細（details）
    detail_lines = []
    if match.age_group:
        detail_lines.append(f"年代: {match.age_group}")
    detail_lines.append(f"試合番号: {match.no}")
    if match.referee:
        detail_lines.append(f"主審: {match.referee}")
    if match.assistant:
        detail_lines.append(f"副審: {match.assistant}")
    details = "\n".join(detail_lines)

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates,
        "location": match.location or "",
        "details": details,
    }

    base_url = "https://calendar.google.com/calendar/render"
    query = urlencode(params, doseq=False, quote_via=quote)
    return f"{base_url}?{query}"


__all__ = ["build_google_calendar_url"]

