import logging
from pathlib import Path
from typing import List, Dict

import camelot
import pdfplumber
import pandas as pd


logger = logging.getLogger(__name__)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    与えられた DataFrame から「日付/時間/会場/対戦」に相当する列を推定して rename する。
    日本語カラム名・英語カラム名の両方をゆるくサポートする。
    """
    if df.empty:
        return df

    col_map: Dict[str, str] = {}
    for col in df.columns:
        col_str = str(col).strip()
        lower = col_str.lower()

        if any(k in col_str for k in ["日付", "月日", "日時"]) or "date" in lower:
            col_map[col] = "date"
        elif any(k in col_str for k in ["時間", "時刻"]) or "time" in lower:
            col_map[col] = "time"
        elif any(k in col_str for k in ["会場", "場所"]) or any(k in lower for k in ["place", "venue", "stadium"]):
            col_map[col] = "place"
        elif any(k in col_str for k in ["対戦", "カード"]) or any(k in lower for k in ["match", "home", "away", "vs"]):
            col_map[col] = "match"

    df = df.rename(columns=col_map)

    # 必須4カラムが揃っているものだけを残す
    required = {"date", "time", "place", "match"}
    if not required.issubset(set(df.columns)):
        missing = required - set(df.columns)
        logger.info("必要カラムが不足しています: %s", ",".join(sorted(missing)))
        return pd.DataFrame(columns=["date", "time", "place", "match"])

    return df[["date", "time", "place", "match"]]


def parse_match_table(pdf_path: Path) -> pd.DataFrame:
    """
    PDF から試合日程テーブルを抽出して
    columns: [date, time, place, match] の DataFrame を返す。

    1. まず Camelot でテーブル抽出を試みる
    2. 失敗した場合は pdfplumber のテーブル検出を試みる
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(str(pdf_path))

    # --- 1. Camelot を試す ---
    try:
        tables = camelot.read_pdf(str(pdf_path), pages="all")
        if tables and tables.n > 0:
            dfs: List[pd.DataFrame] = [t.df for t in tables]
            df_all = pd.concat(dfs, ignore_index=True)
            df_all.columns = [str(c).strip() for c in df_all.iloc[0]]
            df_all = df_all.iloc[1:].reset_index(drop=True)
            normalized = _normalize_columns(df_all)
            if not normalized.empty:
                return normalized
    except Exception as e:  # noqa: BLE001
        logger.exception("Camelot によるテーブル抽出に失敗しました: %s", e)

    # --- 2. pdfplumber のテーブル検出 ---
    rows: List[List[str]] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables or []:
                    for row in table:
                        if any(cell for cell in row):
                            rows.append([cell or "" for cell in row])
    except Exception as e:  # noqa: BLE001
        logger.exception("pdfplumber によるテーブル抽出に失敗しました: %s", e)

    if not rows:
        logger.warning("日程テーブルを検出できません")
        return pd.DataFrame(columns=["date", "time", "place", "match"])

    df = pd.DataFrame(rows)

    # 1行目をヘッダ候補として扱う
    df.columns = [str(c).strip() for c in df.iloc[0]]
    df = df.iloc[1:].reset_index(drop=True)

    normalized = _normalize_columns(df)
    if normalized.empty:
        logger.warning("日程テーブルを検出できません")
    return normalized


__all__ = ["parse_match_table"]

