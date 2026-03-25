from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import List

import html
import streamlit.components.v1 as components

import pandas as pd
import streamlit as st

from modules.pdf_reader import read_pdf_lines
from modules.match_parser import (
    parse_matches_from_lines,
    extract_team_names,
    filter_matches_by_team,
    filter_matches_by_teams,
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
from modules.venue_resolver import (
    load_venue_master,
    normalize_location,
    resolve_location,
    ensure_venue_keywords,
    save_venue_master,
)
from modules.match_snapshot import (
    save_matches_snapshot,
    load_matches_snapshot,
    list_snapshots,
)
from modules.match_diff import diff_matches, build_diff_rows


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdf"
LOGS_DIR = BASE_DIR / "logs"

def _render_special_team_section() -> None:
    """特殊チーム名の追加・削除UI（画面最下部の expander 内で使用）。"""
    with st.expander("特殊チーム設定", expanded=False):
        st.caption("※ 一部チームは正式名称と異なるため必要な場合のみ入力してください。スペースを含むチーム名を登録するとPDF解析で正しく認識されます。")
        special_names = load_special_team_names()
        add_col, _ = st.columns([2, 4])
        with add_col:
            new_name = st.text_input("追加するチーム名", placeholder="例: Regalis F.C", key="new_special_team")
            if st.button("追加", key="btn_add_special"):
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

    st.set_page_config(
        page_title="サッカー日程PDF → Googleカレンダー",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.title("サッカー日程PDF → Googleカレンダー登録ツール")

    st.markdown("PDFからテキストを解析し、**選択したチームの試合** を抽出して Google カレンダーリンクやエクスポートデータを生成します。")

    # 開発者向け（サイドバー）※表示・非表示はここで一元管理。表示順は「全試合データ」の下で統一
    st.sidebar.header("開発者向け")
    show_special_team = st.sidebar.checkbox("特殊チーム名設定を表示", value=False, key="sidebar_show_special_team")
    show_venue_register = st.sidebar.checkbox("会場住所編集", value=False, key="sidebar_show_venue_register")
    show_google_login_button = st.sidebar.checkbox("Google ログインボタンを表示", value=False, key="sidebar_show_google_login_button")
    debug_mode = st.sidebar.checkbox("PDFデバッグモード", value=False, key="sidebar_debug")
    dev_mode = st.sidebar.checkbox("開発者モード", value=False, key="sidebar_dev")

    if "team_options" not in st.session_state:
        st.session_state.team_options = ["ハマーズ"]

    if "selected_teams" not in st.session_state:
        st.session_state.selected_teams = ["ハマーズ"]

    if "pending_selected_teams" not in st.session_state:
        st.session_state.pending_selected_teams = None

    if st.session_state.pending_selected_teams is not None:
        st.session_state.selected_teams = st.session_state.pending_selected_teams
        st.session_state.pending_selected_teams = None
    # チーム名とPDFアップロードを横並び
    col1, col2 = st.columns(2)
    
    with col1:
        selected_teams = st.multiselect(
            "チーム名",
            options=st.session_state.team_options,
            key="selected_teams",
        )


    with col2:
        uploaded_file = st.file_uploader("試合日程PDF", type=["pdf"])

    if not uploaded_file:
        st.info("PDFをアップロードしてください。")
        if show_special_team:
            _render_special_team_section()
        return

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = PDF_DIR / uploaded_file.name
    with open(pdf_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # セッション状態の初期化
    if "lines" not in st.session_state:
        st.session_state.lines = []
        st.session_state.extracted_text = ""
        st.session_state.matches_all = None
        st.session_state.filtered_matches = None
        st.session_state.df_team = None
    
    if "google_logged_in" not in st.session_state:
        st.session_state.google_logged_in = False
    if "diff_result" not in st.session_state:
        st.session_state.diff_result = None
    if "diff_snapshot_name" not in st.session_state:
        st.session_state.diff_snapshot_name = ""
    if "diff_snapshot_pdf_name" not in st.session_state:
        st.session_state.diff_snapshot_pdf_name = ""
    if "diff_target_teams" not in st.session_state:
        st.session_state.diff_target_teams = []
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

            # チーム候補を抽出してセレクト候補を更新
            team_options = extract_team_names(matches_all)
            st.session_state.team_options = team_options

            # デフォルト選択
            if "ハマーズ" in team_options:
                st.session_state.pending_selected_teams = "ハマーズ"
            elif team_options:
                st.session_state.pending_selected_teams = team_options[0]
            else:
                st.session_state.pending_selected_teams = []

            # 会場キーワード登録
            ensure_venue_keywords(
                normalize_location(m.location) for m in matches_all if m.location and str(m.location).strip()
            )

            # ここでは filtered / df_team を作らず、再描画して selectbox 側に反映させる
            st.rerun()

        # セッションからデータを取得
    lines: List[str] = st.session_state.lines
    extracted_text: str = st.session_state.extracted_text
    matches_all = st.session_state.matches_all

    # 現在のセレクト値
    current_teams = st.session_state.selected_teams

    # 抽出済みなら、毎回 current_team で再フィルタする
    if matches_all:
        if not current_teams:
            filtered = list(matches_all)
        else:
            filtered = filter_matches_by_teams(matches_all, current_teams)

        st.session_state.filtered_matches = filtered

        if filtered:
            team_dicts: List[dict] = [m.to_dict() for m in filtered]
            df_team = pd.DataFrame(team_dicts)
            st.session_state.df_team = df_team
        else:
            df_team = pd.DataFrame()
            st.session_state.df_team = df_team
    else:
        filtered = None
        df_team = None
    if matches_all:
        st.markdown("---")
        st.subheader("差分比較")

        snapshot_label = st.text_input(
            "保存名",
            value="base",
            key="snapshot_label",
            help="基準版として保存する名前です。",
        )

        col_diff_1, col_diff_2 = st.columns([1, 2])

        with col_diff_1:
            if st.button("現在の抽出結果を保存", key="save_snapshot_btn"):
                saved_path = save_matches_snapshot(
                    matches=matches_all,
                    pdf_name=uploaded_file.name,
                    label=snapshot_label,
                )
                st.success(f"保存しました: {saved_path.name}")

        snapshots = list_snapshots()
        snapshot_options = {
            f"{item['name']} | {item['label']} | {item['pdf_name']}": item["path"]
            for item in snapshots
        }

        with col_diff_2:
            selected_snapshot_label = st.selectbox(
                "比較する保存済みデータ",
                options=[""] + list(snapshot_options.keys()),
                key="selected_snapshot_path",
            )

        if selected_snapshot_label:
            if st.button("保存済みデータと比較", key="compare_snapshot_btn"):
                snapshot_path = snapshot_options[selected_snapshot_label]
                old_snapshot = load_matches_snapshot(snapshot_path)

                # 保存済みデータ（旧版）と現在PDF（新版）
                old_matches_all = old_snapshot["matches"]
                new_matches_all = matches_all

                # 選択中チームで絞り込み
                if not current_teams:
                    old_matches = list(old_matches_all)
                    new_matches = list(new_matches_all)
                else:
                    old_matches = filter_matches_by_teams(old_matches_all, current_teams)
                    new_matches = filter_matches_by_teams(new_matches_all, current_teams)

                diff_result = diff_matches(old_matches, new_matches)

                st.session_state.diff_result = diff_result
                st.session_state.diff_snapshot_name = old_snapshot["name"]
                st.session_state.diff_snapshot_pdf_name = old_snapshot["pdf_name"]
                st.session_state.diff_target_teams = list(current_teams)

        diff_result = st.session_state.get("diff_result")
        if diff_result:
            added_count = len(diff_result["added"])
            removed_count = len(diff_result["removed"])
            changed_count = len(diff_result["changed"])
            target_teams = st.session_state.get("diff_target_teams", [])
            target_label = "、".join(target_teams) if target_teams else "全チーム"
            st.markdown(
                f"""
**比較結果**
- 対象チーム: {target_label}
- 基準版: {st.session_state.get("diff_snapshot_name", "")}
- 追加: {added_count}件
- 削除: {removed_count}件
- 変更: {changed_count}件
"""
            )

            diff_rows = build_diff_rows(diff_result)

            if diff_rows:
                df_diff = pd.DataFrame(diff_rows)

                diff_csv = df_diff.drop(columns=["_row_type"], errors="ignore").to_csv(index=False)
                st.download_button(
                    "差分CSVエクスポート",
                    data=diff_csv,
                    file_name="match_diff.csv",
                    mime="text/csv",
                    key="download_diff_csv",
                )

                display_df = df_diff.copy()
                html_table = render_diff_table_html(display_df)

                row_count = len(display_df)
                table_height = min(max(260, (row_count + 1) * 42), 720)

                components.html(html_table, height=table_height, scrolling=True)
            else:
                st.info("差分はありません。")
    
    # 抽出前の状態
    if matches_all is None:
        st.info("「試合を抽出する」ボタンを押して抽出を実行してください。")
        return

    # 全試合データ用のDataFrame（末尾のアコーディオンで表示）
    all_dicts: List[dict] = [m.to_dict() for m in matches_all]
    df_all = pd.DataFrame(all_dicts)

    # 選択チーム試合一覧
    st.subheader("選択チーム試合一覧")
    if not filtered:
        selected_label = "、".join(current_teams) if current_teams else "未選択"
        st.info(f"「{selected_label}」に該当する試合は見つかりませんでした。")
        return

    # 表示用に age_group, no を除外し、会場名（location）は正規化して表示
    cols_hidden = ["age_group", "no"]
    df_team_display = df_team.drop(columns=[c for c in cols_hidden if c in df_team.columns], errors="ignore").copy()
    if "location" in df_team_display.columns:
        df_team_display["location"] = df_team_display["location"].apply(lambda x: normalize_location(str(x)) if x else "")
    row_count = len(df_team_display)
    table_height = min(max(220, (row_count + 1) * 35), 700)

    st.dataframe(
        df_team_display,
        use_container_width=True,
        height=table_height,
    )

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
    if show_google_login_button:
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

    # ICS（SUMMARY に対戦カード、DESCRIPTION に対戦カード + 会場・住所）
    ics_lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//soccer-pdf//JP"]
    for m in filtered:
        start_dt, end_dt = m.start_end_datetimes()
        fmt = "%Y%m%dT%H%M%S"
        summary = f"{m.teamA} vs {m.teamB}"
        # 会場 + 住所（venue_resolver.resolve_location を使用）
        loc = ""
        try:
            loc = resolve_location(m.location or "")
        except Exception:
            loc = m.location or ""
        # DESCRIPTION には対戦カードを含めず、会場＋住所のみを入れる（例: 長岡ニュータウン\\n〒940-...）
        desc = loc or summary
        ics_lines.extend(
            [
                "BEGIN:VEVENT",
                f"SUMMARY:{summary}",
                f"DTSTART:{start_dt.strftime(fmt)}",
                f"DTEND:{end_dt.strftime(fmt)}",
                f"DESCRIPTION:{desc}",
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
    # 表示用に age_group, no を除外し、会場名（location）は正規化して表示
    df_all_display = df_all.drop(columns=["age_group", "no"], errors="ignore").copy()
    if "location" in df_all_display.columns:
        df_all_display["location"] = df_all_display["location"].apply(lambda x: normalize_location(str(x)) if x else "")
    with st.expander("全試合データ", expanded=False):
        st.dataframe(df_all_display, use_container_width=True)

    # 開発者向け機能（全試合データの下に区分。表示順: 特殊チーム名設定 → 会場住所編集 → PDFデバッグ → 開発者モード）
    if show_special_team or show_venue_register or debug_mode or dev_mode:
        st.markdown("---")
        st.subheader("開発者向け")

    if show_special_team:
        st.markdown("**特殊チーム名設定を表示**")
        _render_special_team_section()
        st.markdown("---")

    if show_venue_register:
        st.markdown("**会場住所編集**")
        st.caption("取得された会場名（正規化後）が未登録なら自動で keyword に追加されます。住所はセルを編集して Enter で確定後、下の「変更を反映」で保存してください。")
        venue_df = load_venue_master()
        edited_df = st.data_editor(
            venue_df,
            key="venue_editor",
            use_container_width=True,
            num_rows="dynamic",
            column_config={"keyword": "会場名", "address": "住所"},
        )
        if not edited_df.equals(venue_df):
            save_venue_master(edited_df)
            st.success("変更を反映しました。")
            st.rerun()
        if st.button("変更を反映", key="venue_save_btn"):
            save_venue_master(edited_df)
            st.success("変更を反映しました。")
            st.rerun()
        st.markdown("---")

    if debug_mode:
        st.markdown("**PDFデバッグモード**")
        st.text_area("PDF抽出テキスト", extracted_text, height=200, key="debug_extracted")
        st.write("行単位表示")
        for i, line in enumerate(lines, start=1):
            st.write(f"{i}: {line}")
        st.markdown("---")

    if dev_mode and matches_all:
        st.markdown("**開発者モード**")
        st.write("抽出結果（開発者モード）")
        first = matches_all[0]
        st.write(f"DATE = {first.date}")
        st.write(f"LOCATION = {first.location}")
        for idx, m in enumerate(matches_all, start=1):
            st.write(
                f"Line {idx}: age={m.age_group} no={m.no} time={m.time} "
                f"home={m.teamA} away={m.teamB} referee={m.referee} assistant={m.assistant} "
                f"location={m.location}"
            )

def render_diff_table_html(df: pd.DataFrame) -> str:
    columns = [col for col in df.columns if col != "_row_type"]

    def row_style(row_type: str) -> str:
        if row_type in ("before", "removed"):
            return (
                "border-left: 6px solid rgba(255, 90, 90, 0.95);"
                "background: rgba(255, 90, 90, 0.10);"
            )
        if row_type in ("after", "added"):
            return (
                "border-left: 6px solid rgba(60, 200, 120, 0.95);"
                "background: rgba(60, 200, 120, 0.10);"
            )
        return ""

    th_html = "".join(
        f"""
        <th style="
            position: sticky;
            top: 0;
            background: #1e1e1e;
            color: #f5f5f5;
            text-align: left;
            padding: 10px 12px;
            border-bottom: 1px solid rgba(255,255,255,0.12);
            font-weight: 600;
            white-space: nowrap;
        ">{html.escape(str(col))}</th>
        """
        for col in columns
    )

    tr_html_list = []
    for _, row in df.iterrows():
        current_style = row_style(str(row.get("_row_type", "")))
        td_html = "".join(
            f"""
            <td style="
                padding: 9px 12px;
                border-bottom: 1px solid rgba(255,255,255,0.08);
                color: #f5f5f5;
                white-space: nowrap;
            ">{html.escape('' if pd.isna(row[col]) else str(row[col]))}</td>
            """
            for col in columns
        )
        tr_html_list.append(f'<tr style="{current_style}">{td_html}</tr>')

    body_html = "\n".join(tr_html_list)

    return f"""
    <div style="
        overflow-x: auto;
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 10px;
        background: #0e1117;
        font-family: sans-serif;
    ">
        <table style="
            width: 100%;
            border-collapse: collapse;
            background: #0e1117;
            color: #f5f5f5;
            font-size: 14px;
        ">
            <thead>
                <tr>{th_html}</tr>
            </thead>
            <tbody>
                {body_html}
            </tbody>
        </table>
    </div>
    """

if __name__ == "__main__":
    main()

