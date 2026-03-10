# サッカー試合PDF → Googleカレンダー ツール 仕様書

**この README のみから、同一構成のファイルを再生成できる** ことを目的とする。  
本文は仕様の説明、**付録 A** に各ファイルのパスと完全な内容を記載する。

---

## リポジトリの構成と「最新」について

**本リポジトリのアプリは `project/` 配下のみが正式版です。** 必ず `cd project` してから `streamlit run app.py` を実行してください。

- **最新版（project/）に含まれる機能**: チーム名の入力、特殊チーム名の登録（一覧・追加・削除）、Google カレンダー API によるログイン・カレンダー選択・試合の自動登録、CSV/ICS エクスポート、PDF デバッグなど。
- **過去にあった問題**: リポジトリのルート直下に、別仕様の旧アプリ（`app.py`, `modules/pdf_parser.py` 等）が残っており、「チーム名は config/team.json」「特殊チーム名の登録なし」「Google カレンダー API なし」の構成でした。そのため「どちらが最新か」が分かりにくい状態でした。
- **現在の対応**: ルート直下の旧アプリ用ファイルは削除し、**project/ のみがアプリ本体**となるように整理しています。clone 後は `project/` だけを使えば、上記の最新機能がすべて利用できます。

---

## 1 目的・概要

- サッカーリーグの **試合日程PDF** を解析し、指定チームの試合を抽出する。
- **Googleカレンダー登録リンク** の生成と、**Googleログインによるカレンダー自動登録** の両方に対応する。
- **特殊チーム名** は別ファイルで管理し、ダッシュボードから追加・削除できる。
- **CSV / ICS エクスポート** と **PDF解析デバッグ** を提供する。

---

## 2 ディレクトリ・ファイル構成

```
cursor_soccerPDF/
├── README.md
└── project/
    ├── app.py
    ├── requirements.txt
    ├── .gitignore
    ├── modules/
    │   ├── pdf_reader.py
    │   ├── match_parser.py
    │   ├── calendar_link.py
    │   └── google_calendar_api.py
    ├── data/
    │   ├── pdf/
    │   └── special_team_names.txt   # 1行1チーム名（UTF-8）。無ければデフォルト使用。
    └── logs/
        ├── app.log
        ├── parser_error.log
        ├── pdf_debug.log
        └── google_calendar.log
```

- **credentials / token（ローカルと本番の切り替え）**
  - **ローカル**: `project/credentials.json` と `project/token.json` を配置（git 管理しない）。
  - **本番（Streamlit Cloud など）**: 次のいずれかで本番用を使う。
    1. **ファイル名で自動切り替え**: 本番環境では `STREAMLIT_SERVER_RUNNING` が立つため、`credentials_production.json` または `client_secret_*.json`（例: `client_secret_842291968491-....apps.googleusercontent.com.json`）を `project/` に置くとそちらを参照する。token は `token_production.json`。
    2. **環境変数で明示指定**: `GOOGLE_CREDENTIALS_FILE` に credentials のパス、`GOOGLE_TOKEN_FILE` に token のパスを指定する。Streamlit Cloud の「Advanced settings」→ Secrets や環境変数で設定する。
    3. **本番モードの強制**: ローカルでも本番用を使う場合は `USE_PRODUCTION_CREDENTIALS=1` を設定する。
  - 本番用ファイル（`credentials_production.json`, `token_production.json`, `client_secret_*.json`）は .gitignore 済み。

---

## 3 依存関係・起動

- **requirements.txt** の内容: `streamlit`, `pdfplumber`, `pandas`, `google-auth`, `google-auth-oauthlib`, `google-auth-httplib2`, `google-api-python-client`
- 起動: `cd project && pip install -r requirements.txt && streamlit run app.py`（デフォルト http://localhost:8501）

---

## 4 処理フロー（全体）

```
PDFアップロード
  → 特殊チーム名は data/special_team_names.txt から読み込み
  → PDFテキスト抽出 (pdf_reader)
  → 開催日・会場・年代・試合行の解析 (match_parser)
  → チーム名でフィルタ (match_parser)
  → 結果表示
  → カレンダー追加リンク生成 (calendar_link)
  → （任意）Googleログイン → カレンダー選択 → 試合をカレンダー登録 (google_calendar_api)
  → CSV / ICS エクスポート
```

---

## 5 PDF 構造と解析ルール

- **開催日・会場**: 正規表現 `開催日：\s*(\d+月\d+日)\s*会場：(.+)` で `current_date`（YYYY-MM-DD）、`current_location` を取得。年は実行年または行内「○年」から補完。
- **年代グループ**: `^\d{2}[A-Z]?$`（例: 60, 50A）。検出時に `current_age_group` を更新。
- **試合行**: 行頭 `^\d+\s+\d{1,2}:\d{2}`。形式は `No 時刻 Home × Away 主審 副審`。  
  - 通常: `no=tokens[0], time=tokens[1], home=tokens[2], away=tokens[4], referee=tokens[5], assistant=tokens[6]`  
  - 年代付き行: `age_group=tokens[0], no=tokens[1], time=tokens[2], home=tokens[3], away=tokens[5], referee=tokens[6], assistant=tokens[7]`
- **特殊チーム名**: `data/special_team_names.txt` を1行1件で読み込み（無い・空の場合はデフォルト `FC revoltijo`, `fc ziarllo`, `Regalis F.C`）。解析前に各名のスペースを `_` に置換、解析後に `_` をスペースに復元。

---

## 6 データ構造

- **Match**: date, location, age_group, no, time, teamA, teamB, referee, assistant。`to_dict()`, `start_end_datetimes()`（終了=開始+120分）を実装。
- **チームフィルタ**: `team_name in teamA or team_name in teamB` で抽出。

---

## 7 モジュール仕様

- **pdf_reader.py**: `read_pdf_lines(pdf_path: Path) -> List[str]`。pdfplumber で全ページ `extract_text()` し、空でない行を strip して返す。
- **match_parser.py**:  
  - `get_special_team_names_path()`, `load_special_team_names()`, `save_special_team_names(names)`。  
  - `Match` データクラス。  
  - `parse_matches_from_lines(lines, year=None)`（特殊チーム名は `load_special_team_names()` を使用）、`filter_matches_by_team(matches, team_name)`。  
  - 解析エラーは `logs/parser_error.log` に追記。
- **calendar_link.py**: `build_google_calendar_url(match)`。`https://calendar.google.com/calendar/render` に `action=TEMPLATE`, `text`, `dates`, `location`, `details` を URL エンコードして付与。
- **google_calendar_api.py**:  
  - 認証: `project/credentials.json` / `project/token.json`。スコープは `calendar.readonly` と `calendar.events`。  
  - 初回認証: 固定ポート 8080、リダイレクト URI `http://localhost:8080/`。認証 URL をアプリ内表示用に `NeedUserToClickAuthLinkError(auth_url)` を raise。  
  - `get_credentials_path()`, `get_credentials(auth_url_callback=None)`, `list_calendars()`, `insert_events(calendar_id, matches)`。  
  - イベント body: summary=`{teamA} vs {teamB}`, location, description（年代・試合番号・主審・副審）、start/end は dateTime + timeZone: Asia/Tokyo。  
  - ログ: `logs/google_calendar.log`。

---

## 8 Streamlit UI（app.py）

- **レイアウト**: チーム名入力とPDFアップロードは `st.columns(2)` で横並び。セクション番号は付けず `st.subheader` で見出し。
- **順序**: タイトル → チーム名｜PDFアップロード → **特殊チーム名**（入力＋「追加」、一覧＋各行「削除」、`load_special_team_names`/`save_special_team_names` でファイル読み書き）→ PDF未アップロード時はここで return。
- 続き: 「試合を抽出する」→ 結果を `st.session_state`（matches_all, filtered_matches, df_team）に保存。自チーム試合一覧 → Googleカレンダーリンク生成 → **Googleカレンダーへ自動登録**（未ログイン時は「Googleでログイン」、ログイン済みは Google favicon + 「🟢 Googleログイン済み」+「ログアウト」。`google_logged_in` はセッションで管理）→ 登録カレンダー selectbox → 「試合をカレンダー登録」→ 試合エクスポート（CSV / ICS）→ **全試合データ**は `st.expander("全試合データ", expanded=False)` で折りたたみ表示。
- **NeedUserToClickAuthLinkError** 捕捉時は認証 URL を表示し、「認証完了したらもう一度 Googleでログインを押す」と案内。
- CSV ヘッダー: `date,location,age_group,no,time,home,away,referee,assistant`（Match の to_dict のキーに合わせる）。ICS は VEVENT で SUMMARY/DTSTART/DTEND/DESCRIPTION。
- サイドバー: 「開発者向け」で PDFデバッグモード・開発者モードのチェック。デバッグ時は抽出テキスト・行番号付き表示など。

---

## 9 ログ・セキュリティ

- ログ: `logs/app.log`, `logs/parser_error.log`, `logs/pdf_debug.log`, `logs/google_calendar.log`
- **.gitignore**: `credentials.json`, `token.json` を必ず含める。

---

## 10 完成機能一覧

- PDF 解析（開催日・会場・年代・試合行）
- 特殊チーム名のファイル管理とダッシュボードでの追加・削除
- チーム名フィルタ
- Google カレンダー追加リンク生成
- Google ログイン（認証 URL 表示対応）・カレンダー一覧・試合の自動登録・ログアウト
- CSV / ICS エクスポート
- PDF デバッグモード
- 全試合データのアコーディオン表示

---

# 付録 A: 生成するファイル一覧（同一構成の再生成用）

以下に **project/** 以下に生成すべきファイルのパスと内容を記載する。この部分だけから同じ構成のファイルを再現できる。

---

### project/requirements.txt

```
streamlit
pdfplumber
pandas
google-auth
google-auth-oauthlib
google-auth-httplib2
google-api-python-client
```

---

### project/.gitignore

```
credentials.json
token.json
```

---

### project/data/special_team_names.txt（初回またはデフォルト）

1行1チーム名。UTF-8。存在しなくてもアプリはデフォルト一覧で動作する。例:

```
FC revoltijo
fc ziarllo
Regalis F.C
```

---

### project/modules/pdf_reader.py

```python
from pathlib import Path
from typing import List

import pdfplumber


def read_pdf_lines(pdf_path: Path) -> List[str]:
    """
    PDF からテキストを行単位で取得してリストで返す。
    行の前後の空白は strip 済み。
    """
    pdf_path = Path(pdf_path)
    lines: List[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if line:
                    lines.append(line)
    return lines


__all__ = ["read_pdf_lines"]
```

---

### project/modules/calendar_link.py

```python
from __future__ import annotations

from urllib.parse import urlencode, quote

from .match_parser import Match


def build_google_calendar_url(match: Match) -> str:
    """
    仕様に基づき Google カレンダー追加用 URL を生成する。
    """
    start_dt, end_dt = match.start_end_datetimes()
    fmt = "%Y%m%dT%H%M%S"
    dates = f"{start_dt.strftime(fmt)}/{end_dt.strftime(fmt)}"
    title = f"{match.teamA} vs {match.teamB}"
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
```

---

### project/modules/match_parser.py

```python
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Iterable


logger = logging.getLogger(__name__)

DATE_BLOCK_PATTERN = re.compile(r"(\d{1,2})月(\d{1,2})日")
HEADER_LINE_PATTERN = re.compile(r"開催日：\s*(\d+月\d+日)\s*会場：(.+)")
AGE_GROUP_PATTERN = re.compile(r"^\d{2}[A-Z]?$")
MATCH_HEAD_PATTERN = re.compile(r"^\d+\s+\d{1,2}:\d{2}")

DEFAULT_SPECIAL_TEAM_NAMES = [
    "FC revoltijo",
    "fc ziarllo",
    "Regalis F.C",
]

PROJECT_DIR = Path(__file__).resolve().parents[1]
SPECIAL_TEAM_NAMES_FILE = PROJECT_DIR / "data" / "special_team_names.txt"


def get_special_team_names_path() -> Path:
    return SPECIAL_TEAM_NAMES_FILE


def load_special_team_names() -> List[str]:
    if not SPECIAL_TEAM_NAMES_FILE.exists():
        return list(DEFAULT_SPECIAL_TEAM_NAMES)
    lines = SPECIAL_TEAM_NAMES_FILE.read_text(encoding="utf-8").strip().splitlines()
    names = [s.strip() for s in lines if s.strip()]
    return names if names else list(DEFAULT_SPECIAL_TEAM_NAMES)


def save_special_team_names(names: List[str]) -> None:
    SPECIAL_TEAM_NAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    SPECIAL_TEAM_NAMES_FILE.write_text("\n".join(names), encoding="utf-8")


def _apply_special_team_join(line: str, names: List[str] | None = None) -> str:
    if names is None:
        names = load_special_team_names()
    for name in names:
        joined = name.replace(" ", "_")
        line = line.replace(name, joined)
    return line


@dataclass
class Match:
    date: str
    age_group: str | None
    no: int
    time: str
    teamA: str
    teamB: str
    referee: str
    assistant: str
    location: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "age_group": self.age_group or "",
            "no": self.no,
            "time": self.time,
            "teamA": self.teamA,
            "teamB": self.teamB,
            "referee": self.referee,
            "assistant": self.assistant,
            "location": self.location,
        }

    def start_end_datetimes(self) -> tuple[datetime, datetime]:
        start = datetime.strptime(f"{self.date} {self.time}", "%Y-%m-%d %H:%M")
        end = start + timedelta(minutes=120)
        return start, end


def _normalize_date_from_block(text: str, year: int | None = None) -> str | None:
    m = DATE_BLOCK_PATTERN.search(text)
    if not m:
        return None
    month = int(m.group(1))
    day = int(m.group(2))
    if year is None:
        year = datetime.today().year
    dt = datetime(year, month, day)
    return dt.strftime("%Y-%m-%d")


def _log_parse_error(line: str) -> None:
    try:
        logs_dir = Path(__file__).resolve().parents[1] / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        with open(logs_dir / "parser_error.log", "a", encoding="utf-8") as f:
            f.write(f"試合行解析エラー: {line}\n")
    except Exception:
        logger.exception("試合行解析エラーのログ出力に失敗しました")


def _restore_special_team_name(name: str) -> str:
    return name.replace("_", " ")


def parse_matches_from_lines(lines: Iterable[str], year: int | None = None) -> List[Match]:
    special_names = load_special_team_names()
    line_list = list(lines)
    if year is None:
        detected_year = None
        for raw in line_list:
            m_year = re.search(r"(\d{4})年", raw)
            if m_year:
                try:
                    detected_year = int(m_year.group(1))
                    break
                except Exception:
                    continue
        year = detected_year

    current_date: str | None = None
    current_location: str | None = None
    current_age_group: str | None = None
    matches: List[Match] = []

    for raw in line_list:
        original = raw.strip()
        if not original:
            continue
        m_header = HEADER_LINE_PATTERN.search(original)
        if m_header:
            date_text = m_header.group(1)
            loc_text = m_header.group(2).strip()
            norm_date = _normalize_date_from_block(date_text, year=year)
            if norm_date:
                current_date = norm_date
            current_location = loc_text
            continue
        new_date = _normalize_date_from_block(original, year=year)
        if new_date:
            current_date = new_date
            continue
        line = _apply_special_team_join(original, special_names)
        tokens = line.replace("：", ":").split()
        if tokens:
            last_token = tokens[-1]
            if AGE_GROUP_PATTERN.match(last_token):
                current_age_group = last_token
                continue
        if not current_date:
            continue
        if not MATCH_HEAD_PATTERN.match(line):
            if not tokens or len(tokens) < 3:
                continue
            if not (AGE_GROUP_PATTERN.match(tokens[0]) and MATCH_HEAD_PATTERN.match(" ".join(tokens[1:3]))):
                continue
        try:
            if tokens and AGE_GROUP_PATTERN.match(tokens[0]):
                age_group = tokens[0]
                no = int(tokens[1])
                time_str = tokens[2]
                base_idx = 3
            else:
                age_group = current_age_group
                no = int(tokens[0])
                time_str = tokens[1]
                base_idx = 2
            home = _restore_special_team_name(tokens[base_idx])
            away = _restore_special_team_name(tokens[base_idx + 2])
            referee = _restore_special_team_name(tokens[base_idx + 3]) if len(tokens) > base_idx + 3 else ""
            assistant = _restore_special_team_name(tokens[base_idx + 4]) if len(tokens) > base_idx + 4 else ""
            match = Match(
                date=current_date,
                age_group=age_group,
                no=no,
                time=time_str,
                teamA=home,
                teamB=away,
                referee=referee,
                assistant=assistant,
                location=current_location or "",
            )
            matches.append(match)
        except Exception:
            _log_parse_error(line)
            continue
    return matches


def filter_matches_by_team(matches: Iterable[Match], team_name: str) -> List[Match]:
    team_name = (team_name or "").strip()
    if not team_name:
        return list(matches)
    return [m for m in matches if team_name in m.teamA or team_name in m.teamB]


__all__ = [
    "Match",
    "parse_matches_from_lines",
    "filter_matches_by_team",
    "load_special_team_names",
    "save_special_team_names",
    "get_special_team_names_path",
]
```

---

### project/modules/google_calendar_api.py

```python
"""
Google Calendar API v3 による OAuth2 認証とイベント登録。
credentials.json / token.json は project/ 直下に配置する。
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import List, Any

from .match_parser import Match

logger = logging.getLogger(__name__)
PROJECT_DIR = Path(__file__).resolve().parents[1]
TOKEN_PATH = PROJECT_DIR / "token.json"


def _find_credentials_file() -> Path | None:
    p = PROJECT_DIR / "credentials.json"
    return p if p.exists() else None


def get_credentials_path() -> Path | None:
    return _find_credentials_file()


CALENDAR_LOG_PATH = PROJECT_DIR / "logs" / "google_calendar.log"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
TIMEZONE = "Asia/Tokyo"
OAUTH_LOCAL_PORT = 8080


class NeedUserToClickAuthLinkError(Exception):
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
    token_data = {
        "token": creds.token,
        "refresh_token": getattr(creds, "refresh_token", None),
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }
    TOKEN_PATH.write_text(json.dumps(token_data, indent=2), encoding="utf-8")


def get_credentials(auth_url_callback=None):
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
            "project/ に credentials.json がありません。"
            "Google Cloud Console で OAuth クライアント（デスクトップ）を作成し、"
            "credentials.json を project/ に保存してください。"
        )
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            if auth_url_callback is not None:
                redirect_uri = f"http://localhost:{OAUTH_LOCAL_PORT}/"
                flow.redirect_uri = redirect_uri
                auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
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
                server = wsgiref.simple_server.make_server("localhost", OAUTH_LOCAL_PORT, app)
                def _wait_one_request():
                    try:
                        server.handle_request()
                        if app.last_request_uri:
                            authorization_response = app.last_request_uri.replace("http", "https")
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
    from googleapiclient.discovery import build
    creds = get_credentials()
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def list_calendars() -> List[dict[str, Any]]:
    try:
        service = get_calendar_service()
        result = service.calendarList().list().execute()
        items = result.get("items", [])
        return [{"id": c.get("id", ""), "summary": c.get("summary", ""), "primary": c.get("primary", False)} for c in items]
    except Exception as e:
        _get_calendar_logger().exception("カレンダー一覧取得エラー: %s", e)
        raise


def match_to_event_body(match: Match) -> dict[str, Any]:
    start_dt, end_dt = match.start_end_datetimes()
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
        "start": {"dateTime": start_str, "timeZone": TIMEZONE},
        "end": {"dateTime": end_str, "timeZone": TIMEZONE},
    }


def insert_events(calendar_id: str, matches: List[Match]) -> tuple[int, List[str]]:
    log = _get_calendar_logger()
    success_count = 0
    errors: List[str] = []
    try:
        service = get_calendar_service()
    except Exception as e:
        log.exception("Calendar API 初期化エラー: %s", e)
        errors.append(str(e))
        return 0, errors
    for match in matches:
        try:
            body = match_to_event_body(match)
            service.events().insert(calendarId=calendar_id, body=body).execute()
            success_count += 1
            log.info("登録: %s", body.get("summary"))
        except Exception as e:
            msg = f"{match.teamA} vs {match.teamB}: {e}"
            log.error("登録失敗 %s", msg)
            errors.append(msg)
    return success_count, errors
```

---

### project/app.py

```python
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
)
from modules.calendar_link import build_google_calendar_url
from modules.google_calendar_api import (
    get_credentials_path,
    list_calendars,
    insert_events,
    get_credentials,
    NeedUserToClickAuthLinkError,
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
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )


def main() -> None:
    setup_logging()
    st.set_page_config(page_title="サッカー日程PDF → Googleカレンダー", layout="wide")
    st.title("サッカー日程PDF → Googleカレンダー登録ツール")
    st.markdown("PDFからテキストを解析し、**自チームの試合だけ** を抽出して Google カレンダーリンクやエクスポートデータを生成します。")

    col1, col2 = st.columns(2)
    with col1:
        team_name = st.text_input("チーム名", value="ハマーズ", placeholder="例: ハマーズ")
    with col2:
        uploaded_file = st.file_uploader("試合日程PDF", type=["pdf"])

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

    st.sidebar.header("開発者向け")
    debug_mode = st.sidebar.checkbox("PDFデバッグモード")
    dev_mode = st.sidebar.checkbox("開発者モード")

    if "lines" not in st.session_state:
        st.session_state.lines = []
        st.session_state.extracted_text = ""
        st.session_state.matches_all = None
        st.session_state.filtered_matches = None
        st.session_state.df_team = None
    if "google_logged_in" not in st.session_state:
        st.session_state.google_logged_in = False

    extract_clicked = st.button("試合を抽出する")
    if extract_clicked:
        lines = read_pdf_lines(pdf_path)
        extracted_text = "\n".join(lines)
        st.session_state.lines = lines
        st.session_state.extracted_text = extracted_text
        matches_all = parse_matches_from_lines(lines)
        if not matches_all:
            st.warning("試合行を検出できませんでした。PDFの形式を確認してください。")
            st.session_state.matches_all = None
            st.session_state.filtered_matches = None
            st.session_state.df_team = None
        else:
            st.session_state.matches_all = matches_all
            filtered = filter_matches_by_team(matches_all, team_name) if team_name.strip() else matches_all
            st.session_state.filtered_matches = filtered or []
            if filtered:
                st.session_state.df_team = pd.DataFrame([m.to_dict() for m in filtered])
            else:
                st.session_state.df_team = None

    lines = st.session_state.lines
    extracted_text = st.session_state.extracted_text
    matches_all = st.session_state.matches_all
    filtered = st.session_state.filtered_matches
    df_team = st.session_state.df_team

    if matches_all is None:
        st.info("「試合を抽出する」ボタンを押して抽出を実行してください。")
        return

    if debug_mode or dev_mode:
        st.subheader("PDF抽出テキスト（デバッグ）")
        st.text_area("PDF抽出テキスト", extracted_text, height=200)
        st.subheader("行単位表示")
        for i, line in enumerate(lines, start=1):
            st.write(f"{i}: {line}")

    all_dicts = [m.to_dict() for m in matches_all]
    df_all = pd.DataFrame(all_dicts)
    if dev_mode and matches_all:
        st.subheader("抽出結果（開発者モード）")
        first = matches_all[0]
        st.write(f"DATE = {first.date}, LOCATION = {first.location}")
        for idx, m in enumerate(matches_all, start=1):
            st.write(f"Line {idx}: age={m.age_group} no={m.no} time={m.time} home={m.teamA} away={m.teamB} referee={m.referee} assistant={m.assistant}")

    st.subheader("自チーム試合一覧")
    if not filtered:
        st.info(f"「{team_name}」が含まれる試合は見つかりませんでした。")
        return
    st.dataframe(df_team, use_container_width=True)

    st.subheader("Googleカレンダーリンク生成")
    if st.button("カレンダー追加リンク生成"):
        links = [{"date": m.date, "time": m.time, "match": f"{m.teamA} vs {m.teamB}", "link": build_google_calendar_url(m)} for m in filtered]
        st.success("Googleカレンダーリンクを生成しました。")
        st.markdown("各リンクをクリックすると、Googleカレンダーのイベント作成画面が開きます。")
        for item in links:
            st.markdown(f"- [{item['date']} {item['time']}  {item['match']}]({item['link']})")

    st.subheader("Googleカレンダーへ自動登録")
    creds_path = get_credentials_path()
    if not creds_path:
        st.info("自動登録を使うには、Google Cloud Console で OAuth クライアント（デスクトップ）を作成し、**credentials.json** を project/ に保存してください。")
    else:
        if "google_calendars" not in st.session_state:
            st.session_state.google_calendars = None
        show_google_debug = st.checkbox("Google認証のデバッグ表示", value=False, key="google_debug")
        if not st.session_state.google_logged_in:
            if st.button("Googleでログイン"):
                try:
                    with st.status("Googleログイン処理中...", expanded=True) as status:
                        st.info("ブラウザが別タブで開いたら、Googleでログインし「許可」をクリックしてください。開かない場合は下のリンクをクリックしてください。")
                        get_credentials(auth_url_callback=lambda url: None)
                        cal_list = list_calendars()
                        st.session_state.google_calendars = cal_list
                        st.session_state.google_logged_in = True
                        status.update(label="完了", state="complete", expanded=False)
                    st.success("Googleログイン成功。登録先カレンダーを選んで「試合をカレンダー登録」を押してください。")
                except NeedUserToClickAuthLinkError as e:
                    st.warning("ブラウザが自動で開かないため、以下のリンクを**新しいタブで開いて**Googleでログイン・許可してください。")
                    st.markdown(f"[**▶ ここをクリックしてGoogleでログイン**]({e.auth_url})")
                    st.caption("認証が完了したら「認証完了しました」と出るページになります。そのタブを閉じて、もう一度「Googleでログイン」ボタンを押してください。")
                    st.info("※ Google Cloud Console の OAuth クライアントに「リダイレクトURI」として **http://localhost:8080/** を追加してください。")
                except Exception as e:
                    st.error(f"ログインに失敗しました: {e}")
                    with st.expander("エラー詳細（デバッグ用）", expanded=True):
                        st.code(traceback.format_exc(), language="text")
                    if show_google_debug and (BASE_DIR / "logs" / "google_calendar.log").exists():
                        st.code((BASE_DIR / "logs" / "google_calendar.log").read_text(encoding="utf-8")[-4000:], language="text")
        else:
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
            idx = next((i for i, c in enumerate(calendars) if c.get("primary")), 0)
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
        if creds_path and show_google_debug and (BASE_DIR / "logs" / "google_calendar.log").exists():
            with st.expander("デバッグ: google_calendar.log の内容"):
                st.code((BASE_DIR / "logs" / "google_calendar.log").read_text(encoding="utf-8")[-3000:], language="text")

    st.subheader("試合エクスポート")
    csv_data = df_team.to_csv(index=False)
    st.download_button("CSVエクスポート", data=csv_data, file_name="matches.csv", mime="text/csv")
    ics_lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//soccer-pdf//JP"]
    for m in filtered:
        start_dt, end_dt = m.start_end_datetimes()
        fmt = "%Y%m%dT%H%M%S"
        ics_lines.extend([
            "BEGIN:VEVENT", "SUMMARY:サッカー試合",
            f"DTSTART:{start_dt.strftime(fmt)}", f"DTEND:{end_dt.strftime(fmt)}",
            f"DESCRIPTION:{m.teamA} vs {m.teamB}", "END:VEVENT",
        ])
    ics_lines.append("END:VCALENDAR")
    st.download_button("ICSエクスポート", data="\n".join(ics_lines), file_name="matches.ics", mime="text/calendar")

    with st.expander("全試合データ", expanded=False):
        st.dataframe(df_all, use_container_width=True)


if __name__ == "__main__":
    main()
```

---

**付録 A の使い方**: 上記の各コードブロックを、記載したパス（`project/` からの相対パス）にそのまま保存する。`data/pdf/` と `logs/` はアプリ実行時に自動作成される。`credentials.json` と `token.json` は手動で配置する。

この README だけで、同一構成のファイルを再生成できる。


# 追加仕様：Google OAuth をローカル / Streamlit Cloud 両対応にする

## 1 目的

Google Calendar API を利用するための Google OAuth 認証を

- ローカル開発環境
- Streamlit Cloud

の **両方で動作するようにする。**

OAuth の秘密情報は **GitHub に保存しない。**

---

# 2 認証情報の管理

認証情報は以下の方法で管理する。

|環境|認証情報|
|---|---|
ローカル|`.streamlit/secrets.toml`|
Streamlit Cloud|Streamlit Secrets|

---

# 3 Streamlit Secrets 設定

Streamlit Cloud 管理画面

```
App Settings
↓
Secrets
```

以下を登録する。

```
GOOGLE_CLIENT_ID="xxxxxxxxxxxx.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="xxxxxxxxxxxx"
```

---

# 4 ローカル secrets.toml

ローカル環境では以下ファイルを作成する。

```
project/.streamlit/secrets.toml
```

内容

```
GOOGLE_CLIENT_ID="xxxxxxxxxxxx.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="xxxxxxxxxxxx"
```

---

# 5 ディレクトリ構造

```
cursor-soccerPDF
└ project

    app.py

    modules
        google_auth.py
        calendar_api.py

    .streamlit
        secrets.toml
```

---

# 6 .gitignore 設定

以下を `.gitignore` に追加する。

```
.streamlit/secrets.toml
credentials.json
token.json
client_secret*.json
```

理由

```
OAuth秘密鍵をGitHubに公開しない
```

---

# 7 OAuth スコープ

Google Calendar API を利用するためのスコープ

```
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events"
]
```

---

# 8 OAuth 読み込み実装

ファイル

```
modules/google_auth.py
```

---

## Google OAuth Flow 作成

```
import streamlit as st
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events"
]

def create_flow():

    client_config = {
        "installed": {
            "client_id": st.secrets["GOOGLE_CLIENT_ID"],
            "client_secret": st.secrets["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }

    flow = InstalledAppFlow.from_client_config(
        client_config,
        SCOPES
    )

    return flow
```

---

# 9 Googleログイン処理

```
def google_login():

    flow = create_flow()

    creds = flow.run_local_server(port=0)

    return creds
```

---

# 10 Streamlit UI

Googleログインボタン

```
if st.button("Googleログイン"):

    creds = google_login()

    st.session_state["google_creds"] = creds
```

---

# 11 ログイン状態管理

ログイン状態は

```
st.session_state
```

で管理する。

例

```
st.session_state["google_creds"]
```

---

# 12 Googleカレンダー登録

ログイン済みの場合のみ実行する。

```
if "google_creds" in st.session_state:

    service = build(
        "calendar",
        "v3",
        credentials=st.session_state["google_creds"]
    )
```

---

# 13 カレンダーイベント登録

例

```
event = {
    "summary": "サッカー試合",
    "location": location,
    "description": description,
    "start": {
        "dateTime": start_time,
        "timeZone": "Asia/Tokyo"
    },
    "end": {
        "dateTime": end_time,
        "timeZone": "Asia/Tokyo"
    }
}

service.events().insert(
    calendarId="primary",
    body=event
).execute()
```

---

# 14 動作フロー

```
PDFアップロード
↓
試合抽出
↓
Googleログイン
↓
カレンダー登録
```

---

# 15 ローカル起動

```
cd cursor-soccerPDF/project
streamlit run app.py
```

---

# 16 Streamlit Cloud デプロイ

GitHub push

```
git push github master:main
```

Streamlit Cloud が自動で再デプロイする。

---

# 17 動作確認

Googleログインボタンを押す。

以下が表示される。

```
Googleアカウント認証画面
```

認証後

```
Googleカレンダー登録
```

が可能になる。

---

# 18 セキュリティ

以下は GitHub に保存しない。

```
client_secret.json
credentials.json
token.json
secrets.toml
```

認証情報は

```
Streamlit Secrets
```

で管理する。

---

# 19 完成状態

```
GitHub
↓
Streamlit Cloud
↓
Secrets 読み込み
↓
Google OAuth
↓
Googleカレンダー登録
```

ローカルと Streamlit Cloud の両方で  
Googleログインが動作する。