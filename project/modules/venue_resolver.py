"""
会場名 → 住所 のマッピングで Google カレンダー登録時の location を
「会場名\n住所」形式にし、地図・ナビ連携を可能にする。
data/venue_master.csv（keyword, address）を使用。Google Maps API は使わない。
会場名（location）正規化: （）内・※準備以降を削除し、同一会場を揃える。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
VENUE_MASTER_CSV = PROJECT_DIR / "data" / "venue_master.csv"


def load_venue_master() -> pd.DataFrame:
    """会場辞書 CSV を読み込む。ファイルが無い場合は keyword, address の空 DataFrame を返す。"""
    if not VENUE_MASTER_CSV.exists():
        return pd.DataFrame(columns=["keyword", "address"])
    try:
        return pd.read_csv(VENUE_MASTER_CSV, encoding="utf-8")
    except Exception:
        return pd.DataFrame(columns=["keyword", "address"])


def normalize_location(location: str) -> str:
    """
    会場名（location）を正規化する。（）内・※準備以降を削除し、前後空白・連続スペースを整形。
    同一会場が別表記で登録されるのを防ぎ、会場マスタ照合をしやすくする。
    全角括弧（）と半角括弧()の両方に対応する。
    """
    if not (location or "").strip():
        return ""
    s = (location or "").strip()
    # ルール1: （）で囲まれたテキストを削除（全角括弧）
    s = re.sub(r"（.*?）", "", s)
    # ルール1': () で囲まれたテキストを削除（半角括弧）
    s = re.sub(r"\(.*?\)", "", s)
    # ルール2: （ の出現以降を削除（閉じ括弧がない場合・全角）
    s = re.sub(r"（.*", "", s)
    # ルール2': ( の出現以降を削除（半角）
    s = re.sub(r"\(.*", "", s)
    # ルール3・4: ※準備 および ※準備 以降を削除
    s = re.sub(r"※準備.*", "", s)
    # 最終整形: 前後空白削除・連続スペースを1つに
    s = re.sub(r" +", " ", s).strip()
    return s


def resolve_location(venue: str) -> str:
    """
    会場名を正規化したうえで辞書で検索し、住所があれば「会場名\n住所」を返す。無ければ会場名のみ返す。
    Google カレンダーの location に渡すことで地図・ナビ連携が可能になる。
    """
    if not (venue or "").strip():
        return ""
    venue = normalize_location(venue)
    df = load_venue_master()
    if df.empty or "keyword" not in df.columns or "address" not in df.columns:
        return venue
    match = df[df["keyword"].astype(str).str.strip() == venue]
    if len(match) == 0:
        return venue
    address = str(match.iloc[0]["address"]).strip()
    if not address:
        return venue
    return f"{venue}\n{address}"


def add_venue(keyword: str, address: str) -> None:
    """会場辞書に 1 件追加する（CSV に追記）。"""
    keyword = (keyword or "").strip()
    address = (address or "").strip()
    if not keyword:
        return
    df = load_venue_master()
    # 既に同じ keyword があれば上書き（重複登録を防ぐ）
    if not df.empty and "keyword" in df.columns:
        mask = df["keyword"].astype(str).str.strip() == keyword
        if mask.any():
            df.loc[mask, "address"] = address
            df.to_csv(VENUE_MASTER_CSV, index=False, encoding="utf-8")
            return
    df = pd.concat([df, pd.DataFrame([{"keyword": keyword, "address": address}])], ignore_index=True)
    VENUE_MASTER_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(VENUE_MASTER_CSV, index=False, encoding="utf-8")


def ensure_venue_keywords(keywords: Iterable[str]) -> None:
    """
    未登録の会場名（keyword）のみ会場マスタに追加する。address は空。
    取得時に呼び出し、会場住所編集テーブルを一覧で管理する仕様に対応する。
    """
    keys = {str(k).strip() for k in keywords if k and str(k).strip()}
    if not keys:
        return
    df = load_venue_master()
    existing = set()
    if not df.empty and "keyword" in df.columns:
        existing = set(df["keyword"].astype(str).str.strip())
    to_add = keys - existing
    if not to_add:
        return
    VENUE_MASTER_CSV.parent.mkdir(parents=True, exist_ok=True)
    new_rows = pd.DataFrame([{"keyword": k, "address": ""} for k in sorted(to_add)])
    df = pd.concat([df, new_rows], ignore_index=True)
    df.to_csv(VENUE_MASTER_CSV, index=False, encoding="utf-8")


def save_venue_master(df: pd.DataFrame) -> None:
    """
    会場住所編集テーブル（keyword, address）を CSV に保存する。
    keyword はユニークにし、重複は最後の行を残す。
    """
    if df is None or df.empty:
        return
    if "keyword" not in df.columns or "address" not in df.columns:
        return
    out = df[["keyword", "address"]].copy()
    out["keyword"] = out["keyword"].astype(str).str.strip()
    out["address"] = out["address"].astype(str)
    out = out.drop_duplicates(subset=["keyword"], keep="last")
    VENUE_MASTER_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(VENUE_MASTER_CSV, index=False, encoding="utf-8")


__all__ = [
    "load_venue_master",
    "normalize_location",
    "resolve_location",
    "add_venue",
    "ensure_venue_keywords",
    "save_venue_master",
    "VENUE_MASTER_CSV",
]
