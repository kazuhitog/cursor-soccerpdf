from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

from modules.pdf_parser import parse_match_table
from modules.match_extractor import (
    extract_team_matches,
    load_team_name,
)
from modules.calendar_generator import CalendarEvent


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
UPLOADED_DIR = DATA_DIR / "uploaded_pdf"
LOGS_DIR = BASE_DIR / "logs"
TEAM_CONFIG_PATH = CONFIG_DIR / "team.json"


def setup_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / "app.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def main() -> None:
    setup_logging()
    logger = logging.getLogger("app")

    st.set_page_config(page_title="サッカー試合日程 → Googleカレンダー", layout="wide")
    st.title("サッカー試合日程PDF → Googleカレンダー登録ツール")

    st.markdown("PDFから **自チームの試合だけ** を抽出して、Googleカレンダー追加リンクを生成します。")

    # --- サイドバー: チーム名設定 ---
    st.sidebar.header("チーム設定")

    default_team = ""
    try:
        if TEAM_CONFIG_PATH.exists():
            default_team = load_team_name(TEAM_CONFIG_PATH)
    except Exception as e:  # noqa: BLE001
        logger.exception("team.json の読み込みに失敗しました: %s", e)

    team_name = st.sidebar.text_input("自チーム名（例: アルビレッジFC）", value=default_team)

    # --- メイン: PDF アップロード ---
    st.header("① PDFアップロード")
    uploaded_file = st.file_uploader("試合日程PDFをアップロード", type=["pdf"])

    if not uploaded_file:
        st.info("PDFをアップロードしてください。")
        return

    # PDF を保存
    UPLOADED_DIR.mkdir(parents=True, exist_ok=True)
    save_path = UPLOADED_DIR / uploaded_file.name
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.success(f"アップロード完了: {uploaded_file.name}")

    # --- 試合抽出 ---
    st.header("② 試合抽出")
    try:
        df_raw = parse_match_table(save_path)
    except Exception as e:  # noqa: BLE001
        logger.exception("PDF解析でエラーが発生しました: %s", e)
        st.error("日程テーブルを検出できません（PDF解析エラー）。")
        return

    if df_raw.empty:
        st.warning("日程テーブルを検出できません。")
        return

    st.subheader("抽出結果（全試合）")
    st.dataframe(df_raw, use_container_width=True)

    # --- 自チームフィルタ ---
    st.header("③ 自チーム試合のみ抽出")
    if not team_name.strip():
        st.warning("サイドバーから自チーム名を入力してください。")
        return

    matches = extract_team_matches(df_raw, team_name=team_name)
    if not matches:
        st.info(f"「{team_name}」が含まれる試合は見つかりませんでした。")
        return

    match_dicts: List[dict] = [m.to_dict() for m in matches]
    df_team = pd.DataFrame(match_dicts)
    st.subheader("自チームの試合一覧")
    st.dataframe(df_team, use_container_width=True)

    # --- Googleカレンダー追加リンク生成（方法A） ---
    st.header("④ Googleカレンダー追加リンク生成（方法A）")

    if st.button("Googleカレンダー追加リンクを生成"):
        links = []
        for m in matches:
            start, end = m.start_end_datetimes()
            event = CalendarEvent(
                title="サッカー試合",
                description=f"{m.home} vs {m.away}".strip(" vs"),
                location=m.location,
                start=start,
                end=end,
            )
            links.append(
                {
                    "date": m.date,
                    "time": m.time,
                    "match": f"{m.home} vs {m.away}".strip(" vs"),
                    "location": m.location,
                    "link": event.to_google_calendar_link(),
                }
            )

        st.success("Googleカレンダー追加リンクを生成しました。")
        st.markdown("各試合ごとのリンクをクリックすると、Googleカレンダーのイベント作成画面が開きます。")

        for item in links:
            label = f"{item['date']} {item['time']}  {item['match']}  @ {item['location']}"
            st.markdown(f"- [{label}]({item['link']})")


if __name__ == "__main__":
    main()

