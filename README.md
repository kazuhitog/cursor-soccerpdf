# サッカー試合PDF → Googleカレンダー ツール 仕様書

**この README を読み込むだけで、同じ構成・同じアプリを再現して起動できる** ことを目的とする。  
本文で仕様を説明し、**付録 A** に各ファイルのパスと完全な内容を記載する。付録のコードブロックを指定パスに保存し、**付録 B** の手順で起動する。

---

## 追加仕様のまとめ（これまでに取り込んだ仕様）

| 項目 | 内容 |
|------|------|
| **リポジトリ構成** | アプリは `project/` のみ。ルート直下の旧アプリは廃止。 |
| **UI 改善** | チーム名と PDF アップロードを横並び。セクション番号削除。全試合データはアコーディオン表示。Google ログイン状態表示・ログアウト・アイコン。 |
| **特殊チーム名** | `data/special_team_names.txt` で 1 行 1 件管理。ダッシュボードで一覧・追加・削除。 |
| **credentials の切り替え** | ローカル: `credentials.json` / `token.json`。本番: `credentials_production.json` または `client_secret_*.json`、`token_production.json`。環境変数でパス指定可。 |
| **Google OAuth（Web OAuth フロー）** | **run_local_server / wsgiref は使わない**（Streamlit Cloud・スマホで「Address already in use」を防ぐ）。認証は **Streamlit Secrets** のみ: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`。任意で `GOOGLE_REDIRECT_URI`（未設定時は `http://localhost:8501`）。OAuth クライアントは「Web アプリケーション」、リダイレクト URI にアプリ URL と `http://localhost:8501` を追加。`get_auth_url()` → ユーザーがリンクで Google へ → リダイレクトで `?code=xxx` → `process_oauth_callback(code)` でトークン取得・token ファイル保存。UI は `st.link_button("Googleでログイン", auth_url)`。 |

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
    ├── .streamlit/
    │   ├── secrets.toml.example   # コピーして secrets.toml にし、値を設定（git 管理しない）
    │   └── secrets.toml           # ローカル用 OAuth（GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET）
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

- **認証情報（Web OAuth：Streamlit Cloud / スマホ対応）**
  - **Streamlit Secrets 必須**: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`。任意で `GOOGLE_REDIRECT_URI`（省略時はローカル用 `http://localhost:8501`）。ローカルは `project/.streamlit/secrets.toml`、Cloud は App Settings → Secrets。
  - **Google Cloud Console**: OAuth クライアントは「**Web アプリケーション**」。リダイレクト URI に `https://（アプリURL）.streamlit.app` と `http://localhost:8501` を追加。
  - token は `token.json` / `token_production.json` で永続化。Secrets と token は .gitignore で除外。

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
- **google_calendar_api.py**（Web OAuth、run_local_server なし）:  
  - 認証: **Streamlit Secrets** のみ（`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, 任意で `GOOGLE_REDIRECT_URI`）。`_get_web_oauth_secrets()` で取得。token は `token.json` / `token_production.json` で永続化。  
  - `get_auth_url()`: Flow（"web" client_config）で認証 URL を生成し、`st.session_state["oauth_state"]` に state を保存して URL を返す。  
  - `process_oauth_callback(code, state)`: リダイレクト後の `?code=xxx` で呼び、`flow.fetch_token(code=code, state=state)` でトークン取得し token ファイルに保存して Credentials を返す。  
  - `get_credentials()`: token ファイルから読み取りのみ。無ければ `None`（サーバー起動はしない）。  
  - その他: `get_credentials_path()`, `get_calendar_service(creds=None)`, `list_calendars()`, `insert_events(calendar_id, matches)`。スコープ: `calendar.readonly`, `calendar.events`。イベント body: summary / location / description / start・end（Asia/Tokyo）。ログ: `logs/google_calendar.log`。

---

## 8 Streamlit UI（app.py）

- **レイアウト**: チーム名入力とPDFアップロードは `st.columns(2)` で横並び。セクション番号は付けず `st.subheader` で見出し。
- **順序**: タイトル → チーム名｜PDFアップロード → **特殊チーム名**（追加・削除）→ PDF未アップロード時は return → 「試合を抽出する」→ 自チーム試合一覧 → Googleカレンダーリンク生成 → **Googleカレンダーへ自動登録** → 試合エクスポート → 全試合データ（アコーディオン）。
- **Google ログイン（Web OAuth）**: URL に `?code=` があれば `process_oauth_callback(code)` でトークン取得→ログイン済みにし、`st.query_params` から code/state を削除して rerun。未ログイン時は `get_auth_url()` で認証 URL を取得し `st.link_button("Googleでログイン", auth_url)` で表示。ログイン済みは favicon + 「🟢 Googleログイン済み」+「ログアウト」。
- CSV ヘッダー: `date,location,age_group,no,time,home,away,referee,assistant`（Match の to_dict のキーに合わせる）。ICS は VEVENT で SUMMARY/DTSTART/DTEND/DESCRIPTION。
- サイドバー: 「開発者向け」で PDFデバッグモード・開発者モードのチェック。デバッグ時は抽出テキスト・行番号付き表示など。

---

## 9 ログ・セキュリティ

- ログ: `logs/app.log`, `logs/parser_error.log`, `logs/pdf_debug.log`, `logs/google_calendar.log`
- **.gitignore**（OAuth 秘密鍵を GitHub に上げない）: `credentials.json`, `token.json`, `credentials_production.json`, `token_production.json`, `client_secret_*.json`, `.streamlit/secrets.toml`, `__pycache__/`, `logs/`, `data/pdf/`, `.env`, `.DS_Store`

---

## 10 完成機能一覧

- PDF 解析（開催日・会場・年代・試合行）
- 特殊チーム名のファイル管理とダッシュボードでの追加・削除
- チーム名フィルタ
- Google カレンダー追加リンク生成
- Google ログイン（Web OAuth。Secrets 必須。link_button で認証 URL → リダイレクトで code 取得 → トークン保存。ログアウト対応）・カレンダー一覧・試合の自動登録
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
# Python
__pycache__/
*.pyc

# Environment
.env

# Google API
credentials.json
token.json
credentials_production.json
token_production.json
client_secret_*.json

# Streamlit Secrets（OAuth 秘密鍵を GitHub に上げない）
.streamlit/secrets.toml

__pycache__/
logs/
data/pdf/

# OS
.DS_Store
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

### project/.streamlit/secrets.toml.example

このファイルを `secrets.toml` にコピーし、値を設定。OAuth クライアントは「Web アプリケーション」で作成し、リダイレクト URI にアプリ URL と `http://localhost:8501` を追加。

```
# このファイルを secrets.toml にコピーし、値を設定してください。
# OAuth クライアントは「Web アプリケーション」で作成し、
# リダイレクト URI にアプリ URL（Streamlit Cloud）と http://localhost:8501（ローカル）を追加すること。

GOOGLE_CLIENT_ID = "xxxxxxxxxxxx.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "xxxxxxxxxxxx"

# 省略時はローカル用に http://localhost:8501 を使用。Streamlit Cloud ではアプリの URL を指定すること。
# GOOGLE_REDIRECT_URI = "https://cursor-soccerpdf.streamlit.app"
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
        prod = PROJECT_DIR / "credentials_production.json"
        if prod.exists():
            return prod
        for f in sorted(PROJECT_DIR.glob("client_secret_*.json")):
            return f
        return prod

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
    GOOGLE_REDIRECT_URI が無い場合はローカル用に http://localhost:8501 を使用。
    """
    try:
        import streamlit as st
        if "GOOGLE_CLIENT_ID" not in st.secrets or "GOOGLE_CLIENT_SECRET" not in st.secrets:
            return None
        redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
        if not redirect_uri and "GOOGLE_REDIRECT_URI" in st.secrets:
            redirect_uri = str(st.secrets["GOOGLE_REDIRECT_URI"]).strip()
        if not redirect_uri:
            redirect_uri = "http://localhost:8501"
        return {
            "client_id": str(st.secrets["GOOGLE_CLIENT_ID"]).strip(),
            "client_secret": str(st.secrets["GOOGLE_CLIENT_SECRET"]).strip(),
            "redirect_uri": redirect_uri.rstrip("/"),
        }
    except Exception:
        pass
    return None


def get_credentials_path() -> Path | None:
    """認証設定がある場合にパスまたは Secrets 参照を返す（UI 表示用）。"""
    if _get_web_oauth_secrets() is not None:
        return PROJECT_DIR / ".streamlit" / "secrets.toml"
    return _find_credentials_file()


CALENDAR_LOG_PATH = PROJECT_DIR / "logs" / "google_calendar.log"

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
    Secrets に GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI が必要。
    """
    import streamlit as st
    secrets = _get_web_oauth_secrets()
    if not secrets:
        raise FileNotFoundError(
            "Streamlit Secrets に GOOGLE_CLIENT_ID と GOOGLE_CLIENT_SECRET を設定してください。"
            "Streamlit Cloud では App Settings → Secrets、ローカルでは .streamlit/secrets.toml に記載。"
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
    except Exception:
        return None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token_from_flow(creds)
        except Exception:
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
    try:
        service = get_calendar_service()
        result = service.calendarList().list().execute()
        items = result.get("items", [])
        return [
            {"id": c.get("id", ""), "summary": c.get("summary", ""), "primary": c.get("primary", False)}
            for c in items
        ]
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


__all__ = [
    "get_credentials",
    "get_credentials_path",
    "get_auth_url",
    "process_oauth_callback",
    "list_calendars",
    "insert_events",
]
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

        code = st.query_params.get("code")
        if code:
            try:
                process_oauth_callback(code=code)
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
            except Exception as e:
                st.error(f"ログイン処理に失敗しました: {e}")
                with st.expander("エラー詳細", expanded=True):
                    st.code(traceback.format_exc(), language="text")

        if not st.session_state.google_logged_in:
            creds = get_credentials()
            if creds is None:
                try:
                    auth_url = get_auth_url()
                    st.link_button("Googleでログイン", auth_url, type="primary")
                    st.caption("クリックすると Google の認証画面に移動します。許可後、このアプリに戻ります。")
                except FileNotFoundError as e:
                    st.warning(str(e))
                except Exception as e:
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

**付録 A の使い方**: 上記の各コードブロックを、記載したパス（`project/` からの相対パス）にそのまま保存する。`data/pdf/` と `logs/` はアプリ実行時に自動作成される。

---

## 付録 B: 同じアプリを起動する手順（README のみから再現）

1. **ファイルの配置**  
   付録 A のとおり、`project/` 以下に `requirements.txt`, `.gitignore`, `modules/*.py`, `app.py` を保存する。`project/.streamlit/secrets.toml.example` をコピーして `secrets.toml` を作成する（後で値を設定）。

2. **認証情報を用意する**  
   `project/.streamlit/secrets.toml` に `GOOGLE_CLIENT_ID` と `GOOGLE_CLIENT_SECRET` を記載する。Google Cloud Console では OAuth クライアントを「**Web アプリケーション**」で作成し、リダイレクト URI に `https://（アプリURL）.streamlit.app` と `http://localhost:8501` を追加する。任意で `GOOGLE_REDIRECT_URI` を指定（未設定時はローカルで `http://localhost:8501`）。初回ログイン後に `token.json` が自動作成される。

3. **依存のインストールと起動**  
   ```bash
   cd project
   pip install -r requirements.txt
   streamlit run app.py
   ```  
   ブラウザで http://localhost:8501 を開く。

4. **Streamlit Cloud で使う場合**  
   GitHub に push し、Streamlit Cloud でデプロイ。App Settings → Secrets に `GOOGLE_CLIENT_ID` と `GOOGLE_CLIENT_SECRET` を登録。必要なら `GOOGLE_REDIRECT_URI` にアプリの URL を指定する。

この README を読み込むだけで、同じ構成で同じアプリを起動できる。

---

## 追加仕様（Web OAuth）の参照

**「修正仕様（Cursor用）Streamlit Cloud対応 Google OAuth 修正」** は本文・付録 A に統合済みです。

- **要点**: `run_local_server` / `wsgiref` は使わず、**Web OAuth フロー**（認証 URL → ユーザーが Google で許可 → リダイレクトで `?code=xxx` → `process_oauth_callback(code)` でトークン取得）に統一。OAuth クライアントは「Web アプリケーション」、リダイレクト URI にアプリ URL と `http://localhost:8501` を追加。UI は `st.link_button("Googleでログイン", get_auth_url())`。これにより Streamlit Cloud・スマホで「Address already in use」が解消し、同一フローで PC／スマホ／Cloud すべて対応。

# 修正仕様（Cursor用）
# Google OAuth redirect_uri_mismatch 修正

## 1 問題

Streamlit Cloud 上で Google ログインを実行すると以下エラーが発生する。

Error 400: redirect_uri_mismatch

原因は Google OAuth の `redirect_uri` が  
Google Cloud Console に登録されている URI と一致していないため。

---

# 2 原因

Streamlit Cloud のアプリ URL は以下の形式になる。

```
https://cursor-soccerpdf-xxxxxxxxxxxxxxxx.streamlit.app/
```

しかし現在のコードでは

```
https://cursor-soccerpdf.streamlit.app/
```

を redirect_uri として使用しているため一致しない。

OAuth は **完全一致**で URI を検証するため  
この違いで認証が失敗する。

---

# 3 修正方針

以下の2点を修正する。

1. Google Cloud Console に正しい redirect URI を登録
2. アプリコードの redirect_uri を修正

---

# 4 Google Cloud Console 修正

Google Cloud Console を開く

```
https://console.cloud.google.com/apis/credentials
```

対象の OAuth クライアントを編集する。

アプリタイプ

```
Web application
```

---

## Authorized redirect URIs

以下を追加する。

```
https://cursor-soccerpdf-5fzyy7tmi9rhgb3fggjjkk.streamlit.app/
```

さらに将来のために以下も追加する。

```
https://cursor-soccerpdf.streamlit.app/
```

ローカル開発用

```
http://localhost:8501/
```

---

# 5 OAuthコード修正

対象ファイル

```
project/modules/google_calendar_api.py
```

---

## 修正前

```
redirect_uri="https://cursor-soccerpdf.streamlit.app/"
```

---

## 修正後

```
redirect_uri="https://cursor-soccerpdf-5fzyy7tmi9rhgb3fggjjkk.streamlit.app/"
```

---

# 6 Flow作成コード

```
flow = Flow.from_client_config(
    client_config,
    scopes=SCOPES,
    redirect_uri="https://cursor-soccerpdf-5fzyy7tmi9rhgb3fggjjkk.streamlit.app/"
)
```

---

# 7 認証URL生成

```
auth_url, state = flow.authorization_url(
    access_type="offline",
    include_granted_scopes="true"
)
```

---

# 8 Streamlit UI

```
st.link_button(
    "Googleログイン",
    auth_url
)
```

---

# 9 OAuth callback

Google認証後 URL に以下が追加される。

```
?code=xxxxx
```

これを取得する。

```
code = st.query_params.get("code")
```

---

# 10 token取得

```
flow.fetch_token(code=code)

creds = flow.credentials
```

---

# 11 セッション保存

```
st.session_state["google_creds"] = creds
```

---

# 12 カレンダーAPI

```
service = build(
    "calendar",
    "v3",
    credentials=creds
)
```

---

# 13 動作フロー

```
Googleログイン
↓
Google OAuth
↓
Streamlit redirect
↓
code取得
↓
token取得
↓
Googleカレンダー登録
```

---

# 14 動作環境

以下の環境すべてで動作する。

```
PC Chrome
PC Safari
iPhone Safari
iPhone Chrome
Android Chrome
Streamlit Cloud
ローカル開発
```

---

# 15 エラー解消

以下エラーが解消される。

```
Error 400: redirect_uri_mismatch
```

---

# 16 完成状態

```
PDFアップロード
↓
試合抽出
↓
Googleログイン
↓
Googleカレンダー登録
```

スマートフォンからも正常にログイン可能になる。