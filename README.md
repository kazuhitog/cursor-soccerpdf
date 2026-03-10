# サッカー試合PDF → Googleカレンダー ツール 仕様書

このドキュメントのみから **同一アプリを再構築可能** な仕様とする。

---

## 1 目的・概要

- サッカーリーグの **試合日程PDF** を解析し、指定チームの試合を抽出する。
- **Googleカレンダー登録リンク** の生成と、**Googleログインによるカレンダー自動登録** の両方に対応する。
- 加えて **CSV / ICS エクスポート** と **PDF解析デバッグ** を提供する。

---

## 2 ディレクトリ構成

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
    │   └── pdf/
    └── logs/
        ├── app.log
        ├── parser_error.log
        ├── pdf_debug.log
        └── google_calendar.log
```

- **credentials.json** と **token.json** は `project/` 直下に配置する（git 管理しない）。

---

## 3 依存関係・起動

### 3.1 依存ライブラリ

```
streamlit
pdfplumber
pandas
google-auth
google-auth-oauthlib
google-auth-httplib2
google-api-python-client
```

### 3.2 インストール・起動

```bash
cd project
pip install -r requirements.txt
streamlit run app.py
```

デフォルトは **http://localhost:8501** で起動する。

---

## 4 処理フロー（全体）

```
PDFアップロード
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

### 5.1 テキスト例

```
開催日： 4月5日 会場：潟東サルビアサッカー場

60
1 9:30 新潟四十雀60 × NFC60 PRSフューチャーズ SF長岡60
2 10:40 PRSフューチャーズ × SF長岡60 Ｍ.sea60 ピュアーズ60
```

### 5.2 開催日・会場（ヘッダー行）

- パターン: `開催日：\s*(\d+月\d+日)\s*会場：(.+)`
- 取得: `current_date`（年は実行年または指定年で補完し `YYYY-MM-DD`）、`current_location`

### 5.3 年代グループ行

- パターン: `^\d{2}[A-Z]?$`（例: `60`, `50A`, `50B`, `40A` …）
- 検出時に `current_age_group` を更新

### 5.4 試合行判定

- 行頭が「数字 + 空白 + 時刻」: `^\d+\s+\d{1,2}:\d{2}`
- 形式: `No 時刻 Home × Away 主審 副審`（× の前後がホーム・アウェイ）

### 5.5 試合行のトークン分割

- 通常行（年代が直前行で確定している）:  
  `tokens = line.split()` のとき  
  `no=tokens[0], time=tokens[1], home=tokens[2], away=tokens[4], referee=tokens[5], assistant=tokens[6]`
- 年代付き行（行頭が年代）:  
  `age_group=tokens[0], no=tokens[1], time=tokens[2], home=tokens[3], away=tokens[5], referee=tokens[6], assistant=tokens[7]`

### 5.6 特殊チーム名

- スペースを含むチーム名は解析前に一時置換し、解析後に復元する。
- 例: `SPECIAL_TEAM_NAMES = ["FC revoltijo", "fc ziarllo", "Regalis F.C","PC ONZ長岡50"]`  
  前処理: `line.replace("FC revoltijo", "FC_revoltijo")` 等、解析後の表示時: `name.replace("_", " ")`

---

## 6 データ構造

### 6.1 試合（Match）

| 項目 | 例 |
|------|-----|
| date | 2026-04-05 |
| location | 潟東サルビアサッカー場 |
| age_group | 60 |
| no | 1 |
| time | 09:30 |
| home | 新潟四十雀60 |
| away | NFC60 |
| referee | PRSフューチャーズ |
| assistant | SF長岡60 |

### 6.2 チームフィルタ

- UIで指定した `team_name` に対し、`team_name in home` または `team_name in away` で抽出する。

---

## 7 モジュール仕様

### 7.1 pdf_reader.py

- `read_pdf_lines(pdf_path: Path) -> List[str]`  
  PDF を開き、全ページのテキストを `page.extract_text()` で取得し、行リストで返す。

### 7.2 match_parser.py

- `Match`: 上記の date, location, age_group, no, time, home, away, referee, assistant を持つデータクラス。
- `parse_matches_from_lines(lines, year=None) -> List[Match]`: 開催日・会場・年代・試合行の解析ルールに従い Match のリストを返す。
- `filter_matches_by_team(matches, team_name) -> List[Match]`: チーム名でフィルタ。
- 解析エラーは `logs/parser_error.log` に記録する。

### 7.3 calendar_link.py

- `build_google_calendar_url(match: Match) -> str`  
  - ベース: `https://calendar.google.com/calendar/render?action=TEMPLATE`  
  - パラメータ: `text={home} vs {away}`、`dates=YYYYMMDDTHHMMSS/YYYYMMDDTHHMMSS`（終了は開始+120分）、`location={location}`  
  - 日本語・スペースは URL エンコードする。

### 7.4 google_calendar_api.py

- **認証**
  - `project/credentials.json`（Google Cloud の OAuth クライアント「デスクトップ」で取得）を参照。
  - `project/token.json` にアクセス/リフレッシュトークンを保存（初回認証後に作成）。
  - スコープ: `calendar.readonly`（カレンダー一覧取得）、`calendar.events`（イベント登録）。
- **認証フロー（初回・トークンなし）**
  - 固定ポート（例: 8080）でリダイレクト URI を `http://localhost:8080/` に設定。
  - 認証 URL を取得し、**アプリ内に「ここをクリックしてGoogleでログイン」リンクとして表示**する（ブラウザが自動で開かない環境への対応）。
  - 上記ポートでローカルサーバーを 1 リクエスト待ち受け、コールバックでトークン取得 → `token.json` 保存。
  - Google Cloud Console の OAuth クライアントに **リダイレクト URI `http://localhost:8080/`** を追加すること。
- **API**
  - `get_credentials_path() -> Path | None`: credentials.json のパス。
  - `get_credentials(auth_url_callback=None)`: 認証情報を返す。未認証時は `auth_url_callback(url)` で URL を渡し、リンク表示用に **NeedUserToClickAuthLinkError(auth_url)** を raise してよい。
  - `list_calendars() -> List[dict]`: `calendarList.list` で id, summary, primary 等を取得。
  - `insert_events(calendar_id, matches: List[Match]) -> (成功数, エラーメッセージリスト)`: 各 Match を `events.insert` で登録。イベントは下記構造。
- **イベント構造（events.insert の body）**
  - summary: `{home} vs {away}`
  - location: Match の location
  - description: 年代・試合番号・主審・副審をテキストで記載
  - start/end: dateTime を ISO 風（例: 2026-04-05T09:30:00）、timeZone: Asia/Tokyo。試合時間 + 120分で終了。
- エラー・操作ログは `logs/google_calendar.log` に記録する。

---

## 8 Streamlit UI（app.py）

### 8.1 画面構成

1. **チーム名入力**: `st.text_input("チーム名")`（デフォルト例: ハマーズ）
2. **PDFアップロード**: `st.file_uploader` で試合日程PDF
3. **「試合を抽出する」**: 解析実行。結果は `st.session_state` に保存（matches_all, filtered_matches, df_team）し、再実行時もリンク生成・登録まで利用可能にする。
4. **試合一覧**: テーブル表示
5. **「カレンダー追加リンク生成」**: 各試合の Google カレンダー URL を表示（リンク一覧）
6. **⑤-2 Googleカレンダーへ自動登録**
   - **「Googleログイン」**: 認証実行。ブラウザが開かない場合は `NeedUserToClickAuthLinkError` を捕捉し、認証 URL をアプリ内に表示。「認証完了したらもう一度 Googleログインを押す」と案内。
   - ログイン成功後: **登録カレンダー** の `st.selectbox`、**「試合をカレンダー登録」** で一括登録。成功件数・失敗メッセージを表示。
7. **⑥ 試合エクスポート**: CSV ダウンロード、ICS ダウンロード
8. **PDFデバッグモード**（チェック時）: 全テキスト・行番号付き・PDF要素・文字座標などを表示。ログは `logs/pdf_debug.log`

### 8.2 CSV 形式

ヘッダー: `date,location,age_group,no,time,home,away,referee,assistant`。日付・時刻は仕様に合わせた形式で出力。

### 8.3 ICS 形式

- `BEGIN:VEVENT` / `END:VEVENT`
- SUMMARY: `{home} vs {away}`
- DTSTART/DTEND: 日時形式（UTC または TZID に合わせる）
- LOCATION: 会場

---

## 9 ログ・セキュリティ

- **ログ**: `logs/app.log`, `logs/parser_error.log`, `logs/pdf_debug.log`, `logs/google_calendar.log`
- **.gitignore**: `credentials.json`, `token.json` を必ず含める。

---

## 10 完成機能一覧

- PDF 解析（開催日・会場・年代・試合行）
- チーム名フィルタ
- Google カレンダー追加リンク生成
- Google ログインによるカレンダー一覧取得・試合の自動登録（認証 URL 表示対応）
- CSV / ICS エクスポート
- PDF デバッグモード

この仕様書に従って実装すれば、同一のアプリを再構築できる。


# UI改善仕様  
サッカー日程PDF → Googleカレンダー登録ツール

対象ディレクトリ

```
cursor-soccerPDF/project/
```

対象ファイル

```
app.py
```

---

# 1 目的

UIの操作性を向上させるため以下を改善する。

- チーム名入力とPDFアップロードを横並びにする
- セクションタイトルの番号を削除する
- 全試合データをアコーディオン（折りたたみ）表示にする
- Googleログイン状態を視覚的に表示する
- Googleログアウトを可能にする

---

# 2 チーム名入力とPDFアップロードを横並び

## 変更前

```
チーム名入力
PDFアップロード
```

縦並び。

---

## 変更後

```
チーム名入力 | PDFアップロード
```

横並び。

---

## Streamlit実装

```
col1, col2 = st.columns(2)

with col1:
    team_name = st.text_input("チーム名")

with col2:
    uploaded_file = st.file_uploader(
        "試合日程PDF",
        type="pdf"
    )
```

---

# 3 セクション番号削除

## 変更前

```
① チーム名入力
② PDFアップロード
③ 抽出結果
```

---

## 変更後

```
チーム名
試合日程PDF
抽出結果
```

---

## 修正方法

変更前

```
st.header("① チーム名入力")
```

変更後

```
st.subheader("チーム名")
```

---

# 4 全試合抽出のアコーディオン表示

全試合データは通常ユーザーが見る必要がないため  
折りたたみ表示とする。

---

## 表示仕様

```
▶ 全試合データ
```

クリックすると展開。

---

## Streamlit実装

```
with st.expander("全試合データ", expanded=False):

    st.dataframe(all_matches_df)
```

---

# 5 Googleログイン状態表示

Googleログイン状態を  
ユーザーが分かるようにする。

---

## 未ログイン状態

```
[ Googleでログイン ]
```

---

## ログイン状態

```
🟢 Googleログイン済み
[ログアウト]
```

---

# 6 セッション管理

Googleログイン状態は  
Streamlitセッションで管理する。

---

## 初期化

```
if "google_logged_in" not in st.session_state:
    st.session_state.google_logged_in = False
```

---

# 7 Googleログインボタン

```
if not st.session_state.google_logged_in:

    if st.button("Googleでログイン"):

        creds = google_login()

        st.session_state.google_logged_in = True

        st.success("Googleログイン成功")
```

---

# 8 ログイン状態表示

```
else:

    st.markdown("🟢 Googleログイン済み")

    if st.button("ログアウト"):

        st.session_state.google_logged_in = False
```

---

# 9 Googleアイコン表示

Googleログイン状態には  
Googleアイコンを表示する。

---

## GoogleアイコンURL

```
https://www.google.com/favicon.ico
```

---

## 表示コード

```
col1, col2 = st.columns([1,8])

with col1:
    st.image("https://www.google.com/favicon.ico", width=20)

with col2:
    st.write("Googleログイン済み")
```

---

# 10 完成UI構成

最終UIレイアウト

```
---------------------------------

サッカー日程 → Googleカレンダー登録

---------------------------------

チーム名 | PDFアップロード

---------------------------------

Googleログイン

---------------------------------

自チーム試合一覧

---------------------------------

Googleカレンダー登録

---------------------------------

▶ 全試合データ

---------------------------------
```

---

# 11 UIフロー

```
チーム名入力
↓
PDFアップロード
↓
試合抽出
↓
自チーム試合表示
↓
Googleログイン
↓
Googleカレンダー登録
↓
全試合データ確認（折りたたみ）
```

---

# 12 今後のUI改善案（将来）

以下の機能を追加すると操作性が向上する。

---

## 自チーム試合のみ表示スイッチ

```
☑ 自チーム試合のみ表示
```

ON

```
自チーム試合のみ表示
```

OFF

```
全試合表示
```

---

## カレンダー一括登録

```
[全試合をGoogleカレンダー登録]
```

---

## カレンダービュー表示

```
月カレンダー形式で試合表示
```

---

# 13 完成状態

```
チーム名入力
PDFアップロード
↓
試合抽出
↓
Googleログイン
↓
試合をGoogleカレンダー登録
↓
全試合データ確認
```

---

# 完成

サッカー日程PDFから  
**簡単にGoogleカレンダーへ登録できるUI**