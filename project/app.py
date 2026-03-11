from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

from modules.pdf_reader import read_pdf_lines
from modules.match_parser import (
    parse_matches_from_lines,
    filter_matches_by_team,
    load_special_team_names,
    save_special_team_names,
    get_special_team_names_path,
)
from modules.calendar_link import build_google_calendar_url
from modules.google_calendar_api import (
    get_credentials_path,
    get_redirect_uri_for_display,
    list_calendars,
    insert_events,
    get_credentials,
    get_auth_url,
    process_oauth_callback,
)


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

    # チーム名とPDFアップロードを横並び
    col1, col2 = st.columns(2)
    with col1:
        team_name = st.text_input("チーム名", value="ハマーズ", placeholder="例: ハマーズ")
    with col2:
        uploaded_file = st.file_uploader("試合日程PDF", type=["pdf"])

    # 特殊チーム名一覧（追加・削除）
    st.subheader("特殊チーム名")
    st.caption("スペースを含むチーム名を登録すると、PDF解析で正しく認識されます。")
    special_names = load_special_team_names()
    add_col, _ = st.columns([2, 4])
    with add_col:
        new_name = st.text_input("追加するチーム名", placeholder="例: Regalis F.C", key="new_special_team")
        if st.button("追加"):
            name_stripped = (new_name or "").strip()
            if name_stripped and name_stripped not in special_names:
                special_names.append(name_stripped)
                save_special_team_names(special_names)
                st.success(f"「{name_stripped}」を追加しました。")
                st.rerun()
            elif name_stripped in special_names:
                st.warning("すでに登録されています。")
            else:
                st.warning("チーム名を入力してください。")
    if special_names:
        st.markdown("**登録一覧**")
        for i, name in enumerate(special_names):
            del_col1, del_col2 = st.columns([1, 5])
            with del_col1:
                if st.button("削除", key=f"del_special_{i}"):
                    special_names.pop(i)
                    save_special_team_names(special_names)
                    st.rerun()
            with del_col2:
                st.text(name)
    else:
        st.info("登録がありません。上の入力欄から追加してください。")

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
    if "google_logged_in" not in st.session_state:
        st.session_state.google_logged_in = False

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

    # 全試合データ用のDataFrame（末尾のアコーディオンで表示）
    all_dicts: List[dict] = [m.to_dict() for m in matches_all]
    df_all = pd.DataFrame(all_dicts)

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

    # 自チーム試合一覧
    st.subheader("自チーム試合一覧")
    if not filtered:
        st.info(f"「{team_name}」が含まれる試合は見つかりませんでした。")
        return

    st.dataframe(df_team, use_container_width=True)

    # Google カレンダーリンク生成
    st.subheader("Googleカレンダーリンク生成")

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

    # Googleカレンダーへ自動登録（Web OAuth フロー：認証URL → リダイレクト → code でトークン取得）
    st.subheader("Googleカレンダーへ自動登録")
    creds_path = get_credentials_path()
    if not creds_path:
        st.info(
            "自動登録を使うには、`project/.streamlit/secrets.toml`（ローカル）または "
            "Streamlit Cloud の App Settings → Secrets に "
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET を設定してください。"
            "Google Cloud の OAuth クライアントは「Web アプリケーション」で作成し、"
            "リダイレクト URI にアプリの URL（例: https://xxx.streamlit.app）と http://localhost:8501 を追加してください。"
        )
    else:
        if "google_calendars" not in st.session_state:
            st.session_state.google_calendars = None

        show_google_debug = st.checkbox("Google認証のデバッグ表示", value=False, key="google_debug")

        # トラブルシュート: redirect_uri_mismatch / アクセスブロック の案内
        with st.expander("Googleログインでエラーになる場合", expanded=False):
            st.markdown("**Error 400: redirect_uri_mismatch の場合**")
            st.markdown(
                "1. 下の「現在の redirect_uri」をコピーし、"
                "Google Cloud Console → [APIとサービス] → [認証情報] → 対象の OAuth 2.0 クライアント ID → "
                "「認証済みリダイレクト URI」に **同じ文字列を 1 文字も変えず** 追加してください。"
            )
            st.markdown(
                "2. まだエラーなら、末尾の `/` の有無を変えた 2 通りを両方 Console に登録して試してください。"
                "（例: `https://xxx.streamlit.app` と `https://xxx.streamlit.app/`）"
            )
            uri = get_redirect_uri_for_display()
            if uri:
                st.code(uri, language="text")
                st.caption("↑ この値を Google Console の「認証済みリダイレクト URI」に追加")
            else:
                st.caption("（Secrets に GOOGLE_REDIRECT_URI を設定するか、Streamlit Cloud で開いていれば自動で表示されます）")
            st.markdown("---")
            st.markdown("**「このアプリのリクエストは無効です」「アクセスをブロック」の場合**")
            st.markdown(
                "OAuth 同意画面が「テスト」のとき、ログインできるのは **テストユーザーに追加した Google アカウントだけ** です。"
                "登録したアカウント以外でログインするには: "
                "Google Cloud Console → [APIとサービス] → [OAuth 同意画面] → [テストユーザー] で、"
                "ログインしたいメールアドレス（例: lafcreate.biz@gmail.com）を追加してください。"
                "またはアプリを「本番」に公開すると、任意の Google アカウントでログインできます。"
            )

        # コールバック: URL に ?code= が付いていればトークン取得してログイン済みにする
        code = st.query_params.get("code")
        if code:
            try:
                process_oauth_callback(code=code)
                # URL から code/state を外して再表示（二重処理を防ぐ）
                q = dict(st.query_params)
                q.pop("code", None)
                q.pop("state", None)
                try:
                    st.experimental_set_query_params(**q)
                except Exception:
                    pass
                st.session_state.google_logged_in = True
                cal_list = list_calendars()
                st.session_state.google_calendars = cal_list
                st.success("Googleログインに成功しました。登録先カレンダーを選んで「試合をカレンダー登録」を押してください。")
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"ログイン処理に失敗しました: {e}")
                with st.expander("エラー詳細", expanded=True):
                    st.code(traceback.format_exc(), language="text")

        # 未ログイン: 認証URLへのリンクボタン / ログイン済み: 状態表示 + ログアウト
        if not st.session_state.google_logged_in:
            creds = get_credentials()
            if creds is None:
                try:
                    auth_url = get_auth_url()
                    st.link_button("Googleでログイン", auth_url, type="primary")
                    st.caption("クリックすると Google の認証画面に移動します。許可後、このアプリに戻ります。")
                except FileNotFoundError as e:
                    st.warning(str(e))
                except Exception as e:  # noqa: BLE001
                    st.error(f"認証URLの取得に失敗しました: {e}")
                    if show_google_debug:
                        with st.expander("エラー詳細", expanded=True):
                            st.code(traceback.format_exc(), language="text")
            else:
                st.session_state.google_logged_in = True
                cal_list = list_calendars()
                st.session_state.google_calendars = cal_list
                st.rerun()
        else:
            # ログイン済み: Googleアイコン + 状態表示 + ログアウト
            icon_col, text_col = st.columns([1, 8])
            with icon_col:
                st.image("https://www.google.com/favicon.ico", width=24)
            with text_col:
                st.markdown("**🟢 Googleログイン済み**")
            if st.button("ログアウト"):
                st.session_state.google_logged_in = False
                st.session_state.google_calendars = None
                st.rerun()

        calendars = st.session_state.google_calendars
        if calendars:
            options = [f"{c['summary']} ({'メイン' if c['primary'] else ''})" for c in calendars]
            calendar_ids = [c["id"] for c in calendars]
            idx = 0
            for i, c in enumerate(calendars):
                if c.get("primary"):
                    idx = i
                    break
            choice = st.selectbox("登録カレンダー", range(len(options)), format_func=lambda i: options[i], index=idx)
            calendar_id = calendar_ids[choice]
            if st.button("試合をカレンダー登録"):
                success, errs = insert_events(calendar_id, filtered)
                if errs:
                    st.error("登録失敗: " + "; ".join(errs[:3]) + (" ..." if len(errs) > 3 else ""))
                if success:
                    st.success(f"登録完了: {success} 件")
        elif st.session_state.google_calendars is not None and len(st.session_state.google_calendars) == 0:
            st.warning("カレンダーが取得できませんでした。")

        # デバッグ: ログファイルの末尾を常に表示可能に
        if creds_path and show_google_debug:
            log_path = BASE_DIR / "logs" / "google_calendar.log"
            if log_path.exists():
                with st.expander("デバッグ: google_calendar.log の内容"):
                    st.code(log_path.read_text(encoding="utf-8")[-3000:], language="text")

    # 試合エクスポート
    st.subheader("試合エクスポート")

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

    # 全試合データ（折りたたみ）
    with st.expander("全試合データ", expanded=False):
        st.dataframe(df_all, use_container_width=True)


if __name__ == "__main__":
    main()

