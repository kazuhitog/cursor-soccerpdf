"""
Google Calendar API v3 による OAuth2 認証とイベント登録。
ローカル用と本番(Streamlit)用で credentials / token を切り替え可能。

- ローカル: project/credentials.json, project/token.json
- 本番: 環境変数 GOOGLE_CREDENTIALS_FILE で指定、または credentials_production.json / client_secret_*.json
        token は token_production.json または GOOGLE_TOKEN_FILE
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import List, Any

from .match_parser import Match

logger = logging.getLogger(__name__)

# モジュールの親 = project/
PROJECT_DIR = Path(__file__).resolve().parents[1]

# 本番モード: Streamlit Cloud などでは True（環境変数で判定）
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


def get_credentials_path() -> Path | None:
    """現在の credentials ファイルのパス。見つからなければ None。"""
    return _find_credentials_file()


CALENDAR_LOG_PATH = PROJECT_DIR / "logs" / "google_calendar.log"

# カレンダー一覧取得用に readonly、イベント登録用に events
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
TIMEZONE = "Asia/Tokyo"

# 認証用ローカルサーバーのポート（GCPのリダイレクトURIに http://localhost:8080/ を追加すること）
OAUTH_LOCAL_PORT = 8080


class NeedUserToClickAuthLinkError(Exception):
    """ブラウザが自動で開かないため、認証URLを表示してユーザーに手動で開いてもらう場合に投げる。"""
    def __init__(self, auth_url: str):
        self.auth_url = auth_url
        super().__init__(auth_url)


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


def get_credentials(auth_url_callback=None):
    """
    credentials.json と token.json から認証情報を取得。
    初回または token 期限切れ時はブラウザでログインして token.json を保存する。
    auth_url_callback(auth_url) を渡すと、ブラウザを開く代わりにそのコールバックで
    認証URLを渡す（Streamlit などでリンク表示する用）。
    """
    try:
        import wsgiref.simple_server
        import wsgiref.util

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise ImportError(
            "Google Calendar API 用に以下をインストールしてください: "
            "pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client"
        ) from e

    creds_path = _find_credentials_file()
    if not creds_path:
        raise FileNotFoundError(
            "credentials ファイルがありません。"
            "ローカル: project/credentials.json を配置。"
            "本番: project/credentials_production.json または client_secret_*.json を配置するか、"
            "環境変数 GOOGLE_CREDENTIALS_FILE でパスを指定してください。"
        )
    if not creds_path.exists():
        raise FileNotFoundError(f"credentials ファイルが見つかりません: {creds_path}")

    token_path = _get_token_path()
    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:  # noqa: BLE001
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            # 認証URLを先に取得してUIに表示する（ブラウザが自動で開かない環境用）
            if auth_url_callback is not None:
                redirect_uri = f"http://localhost:{OAUTH_LOCAL_PORT}/"
                flow.redirect_uri = redirect_uri
                auth_url, _ = flow.authorization_url(
                    access_type="offline", prompt="consent"
                )

                class _RedirectApp:
                    def __init__(self):
                        self.last_request_uri = None
                    def __call__(self, environ, start_response):
                        start_response("200 OK", [("Content-type", "text/html; charset=utf-8")])
                        self.last_request_uri = wsgiref.util.request_uri(environ)
                        body = "<html><body><p>認証が完了しました。このタブを閉じてアプリに戻り、もう一度「Googleログイン」を押してください。</p></body></html>".encode("utf-8")
                        return [body]

                app = _RedirectApp()
                wsgiref.simple_server.WSGIServer.allow_reuse_address = True
                server = wsgiref.simple_server.make_server(
                    "localhost", OAUTH_LOCAL_PORT, app
                )

                def _wait_one_request():
                    try:
                        server.handle_request()
                        if app.last_request_uri:
                            authorization_response = app.last_request_uri.replace(
                                "http", "https"
                            )
                            flow.fetch_token(authorization_response=authorization_response)
                            _save_token_from_flow(flow.credentials)
                    finally:
                        server.server_close()

                thread = threading.Thread(target=_wait_one_request, daemon=True)
                thread.start()
                if auth_url_callback:
                    auth_url_callback(auth_url)
                raise NeedUserToClickAuthLinkError(auth_url)
            else:
                creds = flow.run_local_server(port=0)
                _save_token_from_flow(creds)

    return creds


def get_calendar_service():
    """認証済み Google Calendar API サービスを返す。"""
    from googleapiclient.discovery import build

    creds = get_credentials()
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


__all__ = ["get_credentials", "get_credentials_path", "list_calendars", "insert_events"]
