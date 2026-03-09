from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

from modules.pdf_reader import read_pdf_lines
from modules.match_parser import (
    parse_matches_from_lines,
    filter_matches_by_team,
)
from modules.calendar_link import build_google_calendar_url


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdf"
LOGS_DIR = BASE_DIR / "logs"


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

    st.set_page_config(page_title="サッカー日程PDF → Googleカレンダー", layout="wide")
    st.title("サッカー日程PDF → Googleカレンダー登録ツール")

    st.markdown("PDFからテキストを解析し、**自チームの試合だけ** を抽出して Google カレンダーリンクやエクスポートデータを生成します。")

    # ① チーム名入力
    st.header("① チーム名入力")
    team_name = st.text_input("チーム名を入力してください（例: ハマーズ）", value="ハマーズ")

    # ② PDFアップロード
    st.header("② PDFアップロード")
    uploaded_file = st.file_uploader("試合日程PDF", type=["pdf"])

    if not uploaded_file:
        st.info("PDFをアップロードしてください。")
        return

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = PDF_DIR / uploaded_file.name
    with open(pdf_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # デバッグ・開発者モード
    st.sidebar.header("開発者向け")
    debug_mode = st.sidebar.checkbox("PDFデバッグモード")
    dev_mode = st.sidebar.checkbox("開発者モード")

    # セッション状態の初期化
    if "lines" not in st.session_state:
        st.session_state.lines = []
        st.session_state.extracted_text = ""
        st.session_state.matches_all = None
        st.session_state.filtered_matches = None
        st.session_state.df_team = None

    # 解析ボタン
    extract_clicked = st.button("試合を抽出する")

    if extract_clicked:
        # テキスト抽出
        lines = read_pdf_lines(pdf_path)
        extracted_text = "\n".join(lines)
        st.session_state.lines = lines
        st.session_state.extracted_text = extracted_text

        # 試合抽出（全試合）
        matches_all = parse_matches_from_lines(lines)
        if not matches_all:
            st.warning("試合行を検出できませんでした。PDFの形式を確認してください。")
            st.session_state.matches_all = None
            st.session_state.filtered_matches = None
            st.session_state.df_team = None
        else:
            st.session_state.matches_all = matches_all

            # チーム名フィルタ
            if not team_name.strip():
                filtered = matches_all
            else:
                filtered = filter_matches_by_team(matches_all, team_name)

            st.session_state.filtered_matches = filtered or []

            if filtered:
                team_dicts: List[dict] = [m.to_dict() for m in filtered]
                st.session_state.df_team = pd.DataFrame(team_dicts)
            else:
                st.session_state.df_team = None

    # セッションからデータを取得
    lines: List[str] = st.session_state.lines
    extracted_text: str = st.session_state.extracted_text
    matches_all = st.session_state.matches_all
    filtered = st.session_state.filtered_matches
    df_team = st.session_state.df_team

    # 抽出前の状態
    if matches_all is None:
        st.info("「試合を抽出する」ボタンを押して抽出を実行してください。")
        return

    # デバッグ表示
    if debug_mode or dev_mode:
        st.subheader("PDF抽出テキスト（デバッグ）")
        st.text_area("PDF抽出テキスト", extracted_text, height=200)

        st.subheader("行単位表示")
        for i, line in enumerate(lines, start=1):
            st.write(f"{i}: {line}")

    # DataFrame 化（全試合表示用）
    all_dicts: List[dict] = [m.to_dict() for m in matches_all]
    df_all = pd.DataFrame(all_dicts)

    st.header("③ 抽出結果（全試合）")
    st.dataframe(df_all, use_container_width=True)

    # 開発者モード用の抽出結果詳細
    if dev_mode and matches_all:
        st.subheader("抽出結果（開発者モード）")
        # 現在の開催日・会場（最初の試合から推定）
        first = matches_all[0]
        st.write(f"DATE = {first.date}")
        st.write(f"LOCATION = {first.location}")
        for idx, m in enumerate(matches_all, start=1):
            st.write(
                f"Line {idx}: age={m.age_group} no={m.no} time={m.time} "
                f"home={m.teamA} away={m.teamB} referee={m.referee} assistant={m.assistant} "
                f"location={m.location}"
            )

    # チーム名フィルタ結果
    st.header("④ 自チーム試合のみ表示")
    if not filtered:
        st.info(f"「{team_name}」が含まれる試合は見つかりませんでした。")
        return

    st.dataframe(df_team, use_container_width=True)

    # Google カレンダーリンク生成
    st.header("⑤ Googleカレンダーリンク生成")

    if st.button("カレンダー追加リンク生成"):
        links = []
        for m in filtered:
            url = build_google_calendar_url(m)
            links.append(
                {
                    "date": m.date,
                    "time": m.time,
                    "match": f"{m.teamA} vs {m.teamB}",
                    "link": url,
                }
            )

        st.success("Googleカレンダーリンクを生成しました。")
        st.markdown("各リンクをクリックすると、Googleカレンダーのイベント作成画面が開きます。")

        for item in links:
            label = f"{item['date']} {item['time']}  {item['match']}"
            st.markdown(f"- [{label}]({item['link']})")

    # エクスポート機能
    st.header("⑥ 試合エクスポート")

    # CSV
    csv_data = df_team.to_csv(index=False)
    st.download_button(
        "CSVエクスポート",
        data=csv_data,
        file_name="matches.csv",
        mime="text/csv",
    )

    # ICS
    ics_lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//soccer-pdf//JP"]
    for m in filtered:
        start_dt, end_dt = m.start_end_datetimes()
        fmt = "%Y%m%dT%H%M%S"
        ics_lines.extend(
            [
                "BEGIN:VEVENT",
                "SUMMARY:サッカー試合",
                f"DTSTART:{start_dt.strftime(fmt)}",
                f"DTEND:{end_dt.strftime(fmt)}",
                f"DESCRIPTION:{m.teamA} vs {m.teamB}",
                "END:VEVENT",
            ]
        )
    ics_lines.append("END:VCALENDAR")
    ics_data = "\n".join(ics_lines)

    st.download_button(
        "ICSエクスポート",
        data=ics_data,
        file_name="matches.ics",
        mime="text/calendar",
    )


if __name__ == "__main__":
    main()

