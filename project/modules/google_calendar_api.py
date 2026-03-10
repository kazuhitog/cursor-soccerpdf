"""
Google Calendar API v3 による OAuth2 認証とイベント登録。
Web OAuth フロー（認証URL方式）で Streamlit Cloud / ローカル / スマホ対応。
run_local_server は使用しない（Address already in use を防ぐ）。

- 認証: Streamlit Secrets に GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI を設定。
  Google Cloud の OAuth クライアントは「Web アプリケーション」で作成し、
  リダイレクト URI に https://xxx.streamlit.app と http://localhost:8501 を追加。
- token: token.json / token_production.json で永続化。
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import List, Any

from .match_parser import Match

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parents[1]


def _is_production_mode() -> bool:
    return (
        os.environ.get("STREAMLIT_SERVER_RUNNING") == "true"
        or os.environ.get("USE_PRODUCTION_CREDENTIALS", "").strip().lower() in ("1", "true", "yes")
    )


def _find_credentials_file() -> Path | None:
    """
    使用する credentials ファイルを決める。
    1) 環境変数 GOOGLE_CREDENTIALS_FILE が設定されていればそのパス（絶対、または project/ からの相対）
    2) 本番モードなら credentials_production.json → client_secret_*.json の順で探す
    3) それ以外は credentials.json（ローカル用）
    """
    env_path = os.environ.get("GOOGLE_CREDENTIALS_FILE", "").strip()
    if env_path:
        p = Path(env_path)
        if not p.is_absolute():
            p = PROJECT_DIR / p
        return p if p.exists() else None

    if _is_production_mode():
        # 本番用: credentials_production.json または client_secret_*.json
        prod = PROJECT_DIR / "credentials_production.json"
        if prod.exists():
            return prod
        for f in sorted(PROJECT_DIR.glob("client_secret_*.json")):
            return f
        # 本番モードだがファイルが無い場合は credentials_production.json を期待
        return prod

    # ローカル: credentials.json
    p = PROJECT_DIR / "credentials.json"
    return p if p.exists() else None


def _get_token_path() -> Path:
    """使用する token ファイルのパス。本番時は token_production.json。"""
    env_path = os.environ.get("GOOGLE_TOKEN_FILE", "").strip()
    if env_path:
        p = Path(env_path)
        return p if p.is_absolute() else (PROJECT_DIR / p)
    if _is_production_mode():
        return PROJECT_DIR / "token_production.json"
    return PROJECT_DIR / "token.json"


def _get_web_oauth_secrets() -> dict | None:
    """
    Streamlit Secrets から Web OAuth 用の client_id, client_secret, redirect_uri を取得。
    ローカル: GOOGLE_REDIRECT_URI 未設定時は http://localhost:8501 を使用。
    Streamlit Cloud: GOOGLE_REDIRECT_URI は必須。ブラウザのアドレスバーと完全一致させる
    （例: https://cursor-soccerpdf-5fzyy7tmi9rhgb3fggjjkk.streamlit.app）。一致しないと redirect_uri_mismatch になる。
    """
    try:
        import streamlit as st
        if "GOOGLE_CLIENT_ID" not in st.secrets or "GOOGLE_CLIENT_SECRET" not in st.secrets:
            return None
        redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
        if not redirect_uri and "GOOGLE_REDIRECT_URI" in st.secrets:
            redirect_uri = str(st.secrets["GOOGLE_REDIRECT_URI"]).strip()
        if not redirect_uri:
            # 本番（Streamlit Cloud）では未設定のままにせず、get_auth_url でエラーにする
            if _is_production_mode():
                redirect_uri = ""
            else:
                redirect_uri = "http://localhost:8501"
        return {
            "client_id": str(st.secrets["GOOGLE_CLIENT_ID"]).strip(),
            "client_secret": str(st.secrets["GOOGLE_CLIENT_SECRET"]).strip(),
            # redirect_uri は Google 側で「完全一致」判定されるため、末尾の / を含めて改変しない
            "redirect_uri": redirect_uri if redirect_uri else "",
        }
    except Exception:  # noqa: BLE001
        pass
    return None


def get_credentials_path() -> Path | None:
    """認証設定がある場合にパスまたは Secrets 参照を返す（UI 表示用）。"""
    if _get_web_oauth_secrets() is not None:
        return PROJECT_DIR / ".streamlit" / "secrets.toml"
    return _find_credentials_file()


CALENDAR_LOG_PATH = PROJECT_DIR / "logs" / "google_calendar.log"

# カレンダー一覧取得用に readonly、イベント登録用に events
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
TIMEZONE = "Asia/Tokyo"


def _get_calendar_logger() -> logging.Logger:
    log_dir = CALENDAR_LOG_PATH.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("google_calendar")
    if not log.handlers:
        h = logging.FileHandler(CALENDAR_LOG_PATH, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
    return log


def _save_token_from_flow(creds) -> None:
    """Credentials を token ファイルに保存（ローカル/本番でパスが異なる）。"""
    token_path = _get_token_path()
    token_data = {
        "token": creds.token,
        "refresh_token": getattr(creds, "refresh_token", None),
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(token_data, indent=2), encoding="utf-8")


def _build_web_flow(redirect_uri: str, client_id: str, client_secret: str):
    """Web OAuth 用の Flow を組み立てる。"""
    from google_auth_oauthlib.flow import Flow
    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )


def get_auth_url() -> str:
    """
    Web OAuth 用の認証 URL を返す。state は st.session_state["oauth_state"] に保存される。
    Secrets に GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET が必要。Streamlit Cloud では GOOGLE_REDIRECT_URI も必須。
    """
    import streamlit as st
    secrets = _get_web_oauth_secrets()
    if not secrets:
        raise FileNotFoundError(
            "Streamlit Secrets に GOOGLE_CLIENT_ID と GOOGLE_CLIENT_SECRET を設定してください。"
            "Streamlit Cloud では App Settings → Secrets、ローカルでは .streamlit/secrets.toml に記載。"
        )
    if not (secrets.get("redirect_uri") or "").strip():
        raise FileNotFoundError(
            "Streamlit Cloud では GOOGLE_REDIRECT_URI の設定が必須です。"
            "ブラウザのアドレスバーに表示されているアプリの URL（例: https://cursor-soccerpdf-5fzyy7tmi9rhgb3fggjjkk.streamlit.app）を、"
            "1) Google Cloud Console の「認証済みリダイレクト URI」に追加し、"
            "2) App Settings → Secrets に GOOGLE_REDIRECT_URI として同じ URL を設定してください。"
            "完全一致しないと Error 400: redirect_uri_mismatch になります。"
        )
    flow = _build_web_flow(
        secrets["redirect_uri"],
        secrets["client_id"],
        secrets["client_secret"],
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    st.session_state["oauth_state"] = state
    return auth_url


def process_oauth_callback(code: str, state: str | None = None):
    """
    リダイレクト後に ?code=xxx で戻ってきたとき、code と state でトークン取得し token ファイルに保存して Credentials を返す。
    """
    import streamlit as st
    secrets = _get_web_oauth_secrets()
    if not secrets:
        raise FileNotFoundError("Secrets が設定されていません。")
    if not (secrets.get("redirect_uri") or "").strip():
        raise FileNotFoundError(
            "GOOGLE_REDIRECT_URI を設定してください（Streamlit Cloud では必須）。"
            "アプリの URL を Google Cloud Console の認証済みリダイレクト URI と Secrets の両方に同じ値で設定してください。"
        )
    saved_state = st.session_state.get("oauth_state") if state is None else state
    flow = _build_web_flow(
        secrets["redirect_uri"],
        secrets["client_id"],
        secrets["client_secret"],
    )
    flow.fetch_token(code=code, state=saved_state)
    creds = flow.credentials
    _save_token_from_flow(creds)
    if "oauth_state" in st.session_state:
        del st.session_state["oauth_state"]
    return creds


def get_credentials():
    """
    token ファイルから認証情報を取得。有効なトークンが無ければ None を返す。
    初回ログインは get_auth_url() で認証 URL を取得し、ユーザーがログイン後に
    リダイレクトで戻ってきたら process_oauth_callback(code) でトークン取得すること。
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = _get_token_path()
    if not token_path.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except Exception:  # noqa: BLE001
        return None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token_from_flow(creds)
        except Exception:  # noqa: BLE001
            pass
    return creds if (creds and creds.valid) else None


def get_calendar_service(creds=None):
    """認証済み Google Calendar API サービスを返す。creds が渡されていればそれを使い、なければ token ファイルから取得。"""
    from googleapiclient.discovery import build

    creds = creds or get_credentials()
    if creds is None:
        raise ValueError("認証されていません。Googleログインを実行してください。")
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def list_calendars() -> List[dict[str, Any]]:
    """
    ユーザーのカレンダー一覧を取得。
    [{"id": "...", "summary": "...", "primary": True/False}, ...]
    """
    try:
        service = get_calendar_service()
        result = service.calendarList().list().execute()
        items = result.get("items", [])
        return [
            {
                "id": c.get("id", ""),
                "summary": c.get("summary", ""),
                "primary": c.get("primary", False),
            }
            for c in items
        ]
    except Exception as e:  # noqa: BLE001
        _get_calendar_logger().exception("カレンダー一覧取得エラー: %s", e)
        raise


def match_to_event_body(match: Match) -> dict[str, Any]:
    """仕様 #40 のイベント構造を生成。"""
    start_dt, end_dt = match.start_end_datetimes()
    # ISO format with timezone
    start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

    detail_lines = []
    if match.age_group:
        detail_lines.append(f"年代: {match.age_group}")
    detail_lines.append(f"試合番号: {match.no}")
    if match.referee:
        detail_lines.append(f"主審: {match.referee}")
    if match.assistant:
        detail_lines.append(f"副審: {match.assistant}")
    description = "\n".join(detail_lines)

    return {
        "summary": f"{match.teamA} vs {match.teamB}",
        "location": match.location or "",
        "description": description,
        "start": {
            "dateTime": start_str,
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end_str,
            "timeZone": TIMEZONE,
        },
    }


def insert_events(calendar_id: str, matches: List[Match]) -> tuple[int, List[str]]:
    """
    指定カレンダーに試合イベントを一括登録。
    戻り値: (成功数, エラーメッセージのリスト)
    """
    log = _get_calendar_logger()
    success_count = 0
    errors: List[str] = []

    try:
        service = get_calendar_service()
    except Exception as e:  # noqa: BLE001
        log.exception("Calendar API 初期化エラー: %s", e)
        errors.append(str(e))
        return 0, errors

    for match in matches:
        try:
            body = match_to_event_body(match)
            service.events().insert(calendarId=calendar_id, body=body).execute()
            success_count += 1
            log.info("登録: %s", body.get("summary"))
        except Exception as e:  # noqa: BLE001
            msg = f"{match.teamA} vs {match.teamB}: {e}"
            log.error("登録失敗 %s", msg)
            errors.append(msg)

    return success_count, errors


__all__ = [
    "get_credentials",
    "get_credentials_path",
    "get_auth_url",
    "process_oauth_callback",
    "list_calendars",
    "insert_events",
]
