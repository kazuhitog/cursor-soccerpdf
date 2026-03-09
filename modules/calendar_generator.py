from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict
from urllib.parse import urlencode, quote


logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    title: str
    description: str
    location: str
    start: datetime
    end: datetime

    def to_google_calendar_link(self) -> str:
        """
        Google カレンダー追加リンク（方法A）を生成。

        例:
        https://calendar.google.com/calendar/render?action=TEMPLATE
        &text=サッカー試合
        &dates=20260403T190000/20260403T210000
        &location=アルビレッジ
        &details=アルビレッジFC vs 新潟SC
        """
        base_url = "https://calendar.google.com/calendar/render"
        date_format = "%Y%m%dT%H%M%S"
        dates = f"{self.start.strftime(date_format)}/{self.end.strftime(date_format)}"

        params: Dict[str, str] = {
            "action": "TEMPLATE",
            "text": self.title,
            "dates": dates,
            "location": self.location,
            "details": self.description,
        }

        # 日本語などを安全に扱うために doseq=False で urlencode
        query = urlencode(params, doseq=False, quote_via=quote)
        return f"{base_url}?{query}"


__all__ = ["CalendarEvent"]

