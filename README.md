# サッカー日程PDF → Googleカレンダー登録ツール仕様

## プロジェクトディレクトリ

```
cursor-soccerPDF/project/
```

---

# 1 目的

リーグから配布される **試合日程PDF** から  
任意のチームの試合のみ抽出し  
Googleカレンダーへ登録するツール。

目的

- 手動入力の削減
- 試合登録ミス防止
- チーム共有

---

# 2 システム構成

処理フロー

```
PDFアップロード
     ↓
テキスト抽出
     ↓
日付ブロック解析
     ↓
試合行抽出
     ↓
チーム名フィルタ
     ↓
Googleカレンダーリンク生成
```

---

# 3 入力PDFフォーマット

PDF内テキストは以下のような構造

```
4月5日

1 9:30 新潟四十雀60 × NFC60
2 10:40 PRSフューチャーズ × SF長岡60
3 11:50 Ｍ.sea60 × ピュアーズ60
```

抽出対象

|項目|例|
|---|---|
日付|4月5日|
開始時間|9:30|
ホーム|新潟四十雀60|
アウェイ|NFC60|

---

# 4 チーム名設定（変更可能）

設定はUIから入力

例

```
自チーム名

新潟四十雀60
```

または

```
M.sea60
```

---

# 5 抽出条件

試合行に

```
team_name
```

が含まれる場合のみ抽出

例

```
新潟四十雀60 × NFC60
```

または

```
NFC60 × 新潟四十雀60
```

---

# 6 データ抽出ロジック

正規表現

```
(\d+:\d+)\s+(.+?)\s×\s(.+)
```

取得データ

```
time
teamA
teamB
```

---

# 7 日付管理

PDF内に

```
4月5日
4月12日
```

などの日付ブロックがある。

現在の解析日付として保持する。

例

```
current_date = 2026-04-05
```

---

# 8 内部データ構造

```
match = {

date: "2026-04-05",
time: "09:30",
teamA: "新潟四十雀60",
teamB: "NFC60",
location: ""
}
```

---

# 9 Googleカレンダー登録

GoogleカレンダーURL生成

```
https://calendar.google.com/calendar/render?action=TEMPLATE
&text=サッカー試合
&dates=20260405T093000/20260405T113000
&details=新潟四十雀60 vs NFC60
```

---

# 10 試合時間

終了時間は固定

```
120分
```

例

```
9:30 → 11:30
```

---

# 11 UI（Streamlit）

画面構成

### ① チーム名入力

```
st.text_input("チーム名")
```

例

```
M.sea60
```

---

### ② PDFアップロード

```
st.file_uploader("試合日程PDF")
```

---

### ③ 抽出結果

|日付|時間|対戦|
|---|---|---|
|4/5|9:30|新潟四十雀60 vs NFC60|

---

### ④ Googleカレンダー登録

```
カレンダー追加リンク生成
```

---

# 12 ディレクトリ構造

```
cursor-soccerPDF
└ project

    app.py

    modules
        pdf_reader.py
        match_parser.py
        calendar_link.py

    data
        pdf

    logs
        app.log
```

---

# 13 使用ライブラリ

```
streamlit
pdfplumber
pandas
regex
datetime
```

インストール

```
pip install streamlit pdfplumber pandas
```

---

# 14 MVP（最初に作る機能）

```
PDFアップロード
↓
試合抽出
↓
チーム名フィルタ
↓
Googleカレンダーリンク生成
```

---

# 15 実行

```
cd cursor-soccerPDF/project

streamlit run app.py
```

---

# 16 将来拡張

## OCR対応

画像PDFにも対応

```
Tesseract OCR
```

---

## Googleカレンダー自動登録

API使用

```
Google Calendar API
```

---

## LINE通知

```
試合前日
試合2時間前
```

---

# 17 完成状態

```
PDFを入れる
↓
チーム名入力
↓
自チーム試合だけ抽出
↓
Googleカレンダーリンク生成
```

---

# 完成

サッカー試合日程を  
**10秒でGoogleカレンダー登録できるツール**


## 追加仕様

# 追加仕様

## 18 試合エクスポート機能

抽出された試合データをエクスポートできるボタンを追加する。

目的

・Googleカレンダー以外でも利用可能  
・CSV保存  
・ICSカレンダーファイル生成  

---

### UI

```
試合抽出
↓
抽出結果テーブル表示
↓
[試合エクスポート]
```

---

### エクスポート形式

#### CSV

```
date,time,teamA,teamB,location
2026-04-05,09:30,新潟四十雀60,NFC60,
2026-04-05,11:50,M.sea60,ピュアーズ60,
```

---

#### ICS（カレンダーファイル）

Googleカレンダー  
Appleカレンダー  
Outlook  

にインポート可能

例

```
BEGIN:VEVENT
SUMMARY:サッカー試合
DTSTART:20260405T093000
DTEND:20260405T113000
DESCRIPTION:新潟四十雀60 vs NFC60
END:VEVENT
```

---

### Streamlit UI

```
st.download_button(
   "CSVエクスポート",
   csv_data
)
```

```
st.download_button(
   "ICSエクスポート",
   ics_data
)
```

---

# 19 PDF構造デバッグ機能

日程テーブルが抽出できない場合  
PDF内部の構造を確認できる機能を追加する。

目的

・PDF構造確認  
・テキスト抽出の調整  
・正規表現の修正  

---

## デバッグモード

UIにチェックボックスを追加

```
[ ] PDFデバッグモード
```

ONにすると以下を表示する。

---

## 表示内容

### 1 PDF全テキスト

PDFから抽出したテキストをそのまま表示

```
st.text_area(
    "PDF抽出テキスト",
    extracted_text
)
```

これにより

```
改行
スペース
文字崩れ
```

を確認できる。

---

### 2 行単位表示

PDFテキストを行単位で表示

例

```
1: 4月5日
2: 9時～17時
3: 1 9:30 新潟四十雀60 × NFC60
4: 2 10:40 PRSフューチャーズ × SF長岡60
```

Streamlit

```
for i,line in enumerate(lines):
    st.write(i,line)
```

---

### 3 PDF要素確認

pdfplumberでページ要素を確認

表示可能な要素

```
text
rect
line
curve
char
```

例

```
with pdfplumber.open(file) as pdf:
    page = pdf.pages[0]
    st.write(page.objects)
```

これにより

```
テキストPDF
画像PDF
```

か判定できる。

---

### 4 文字座標確認

PDFの文字座標を表示

```
page.chars
```

例

```
text: 新
x0: 120
y0: 540
```

これにより

```
表形式
座標ベース
```

か判断できる。

---

# 20 OCR判定

もし

```
page.extract_text() == None
```

の場合

PDFは

```
画像PDF
```

である可能性が高い。

その場合

```
OCRモード
```

を案内する。

---

# 21 PDF解析モード切替

UI

```
解析モード

○ テキスト解析
○ OCR解析
```

---

# 22 ログ機能

解析結果をログ保存

```
logs/pdf_debug.log
```

保存内容

```
PDFファイル名
抽出テキスト
解析結果
エラー内容
```

---

# 23 開発者モード

UIに表示

```
開発者モード
```

ONにすると

表示される

```
PDF全テキスト
行番号
PDF要素
抽出結果
```

---

# 24 完成イメージ

```
PDFアップロード
↓
チーム名入力
↓
試合抽出
↓
結果表示

[Googleカレンダー追加]

[CSVエクスポート]

[ICSエクスポート]

[PDFデバッグモード]
```

---

# 25 この機能のメリット

PDF形式が違っても

```
自分で解析調整可能
```

になる。

これは

```
リーグPDF対応
```

で非常に重要。

追加

# 追加仕様：試合日程抽出ルール

## 26 試合日程抽出ロジック

PDFから抽出したテキストを行単位で解析し  
試合日程データを抽出する。

---

# 26.1 基本構造

PDFテキストは以下のような構造となる。

```
1〜2行    タイトルなど
3〜6行    項目名
7〜12行   試合日程
```

例

```
No. 開始時間 H × A 主審 副審
```

---

# 26.2 試合データ構造

試合データは以下の順序で並ぶ。

```
No 開始時間 H × A 主審 副審
```

例

```
1 9:30 新潟四十雀60 × NFC60 PRSフューチャーズ SF長岡60
```

抽出データ

|項目|例|
|---|---|
No|1|
開始時間|9:30|
ホーム|新潟四十雀60|
アウェイ|NFC60|
主審|PRSフューチャーズ|
副審|SF長岡60|

---

# 26.3 年代グループ

試合の途中に **年代グループ名** が入る。

例

```
60
50A
50B
40A
40B
40C
70
```

この行は **試合データではない。**

---

## 年代行の判定条件

以下に一致する場合

```
^\d{2}[A-Z]?$ 
```

例

```
60
50A
40B
70
```

---

## 処理

年代行を検出した場合

```
current_age_group
```

を更新する。

例

```
current_age_group = "60"
```

---

# 26.4 試合行判定

試合行は以下条件を満たす。

```
先頭が試合番号
```

正規表現

```
^\d+\s+\d{1,2}:\d{2}
```

例

```
1 9:30 新潟四十雀60 × NFC60 PRSフューチャーズ SF長岡60
```

---

# 26.5 試合行解析

試合行は以下の形式

```
No 時間 H × A 主審 副審
```

例

```
1 9:30 新潟四十雀60 × NFC60 PRSフューチャーズ SF長岡60
```

解析ルール

```
No = token[0]
time = token[1]

home = token[2]
away = token[4]

referee = token[5]
assistant = token[6]
```

※ × は区切り記号

---

# 26.6 年代が行頭に入るケース

例

```
60 2 10:40 PRSフューチャーズ × SF長岡60 Ｍ.sea60 ピュアーズ60
```

解析

```
age_group = token[0]

No = token[1]
time = token[2]

home = token[3]
away = token[5]

referee = token[6]
assistant = token[7]
```

---

# 26.7 年代のみ行

例

```
22: 40A
```

この場合

```
current_age_group = 40A
```

として保存する。

---

# 26.8 完成データ構造

```
match = {

date: "2026-04-12",
age_group: "50A",
no: 5,
time: "14:10",

home: "レジェンド大崎",
away: "PC ONZ長岡50",

referee: "F.C.bolamigo",
assistant: "SF長岡50"

}
```

---

# 26.9 抽出アルゴリズム

処理フロー

```
PDFテキスト取得
↓
改行で分割
↓
1行ずつ解析
```

---

## 疑似コード

```
for line in lines:

    if 年代行:
        current_age_group 更新
        continue

    if 試合行:

        if 年代付き:
            age = token[0]
            no = token[1]

        else:
            age = current_age_group
            no = token[0]

        match生成
```

---

# 26.10 出力データ

最終抽出データ

```
date
age_group
no
time
home
away
referee
assistant
```

---

# 26.11 例

抽出結果

```
date: 4/5
age_group: 60
no: 1
time: 9:30
home: 新潟四十雀60
away: NFC60
```

```
date: 4/5
age_group: 60
no: 2
time: 10:40
home: PRSフューチャーズ
away: SF長岡60
```

---

# 26.12 エラー処理

試合行解析失敗時

ログ出力

```
試合行解析エラー
line内容
```

保存

```
logs/parser_error.log
```

---

# 26.13 デバッグ表示

開発者モードONの場合

表示

```
行番号
抽出データ
年代
```

例

```
Line 8
age=60
no=2
time=10:40
home=PRSフューチャーズ
away=SF長岡60
```

---

# 26.14 抽出結果

抽出された試合を

```
table表示
CSV出力
Googleカレンダー生成
```

に利用する。

# 追加仕様：Googleカレンダー登録リンク生成

## 27 カレンダーイベントタイトル

Googleカレンダー登録リンク生成時に  
イベントタイトルに **対戦カード（H vs A）** を設定する。

---

# 27.1 タイトル生成ルール

タイトルは以下の形式とする。

```
{ホームチーム} vs {アウェイチーム}
```

例

```
FCF vs ハマーズ
```

---

# 27.2 GoogleカレンダーURL

生成URL

```
https://calendar.google.com/calendar/render?action=TEMPLATE
```

パラメータ

|パラメータ|内容|
|---|---|
text|イベントタイトル|
dates|開始終了日時|
location|会場|
details|試合詳細|

---

# 27.3 タイトル設定

```
text = "{home} vs {away}"
```

例

```
FCF vs ハマーズ
```

---

# 27.4 説明（details）

説明には試合情報を記載

```
年代: {age_group}
試合番号: {no}
主審: {referee}
副審: {assistant}
```

例

```
年代: 50A
試合番号: 5
主審: F.C.bolamigo
副審: SF長岡50
```

---

# 27.5 日時

開始時間

```
{date} {time}
```

終了時間

```
開始 + 120分
```

例

```
開始: 20260405T093000
終了: 20260405T113000
```

---

# 27.6 生成URL例

例

```
https://calendar.google.com/calendar/render?action=TEMPLATE
&text=FCF%20vs%20ハマーズ
&dates=20260412T142000/20260412T162000
&location=アルビレッジ
&details=年代%3A50A%0A主審%3AF.C.bolamigo%0A副審%3ASF長岡50
```

---

# 27.7 URLエンコード

GoogleカレンダーURLでは  
日本語・スペースをURLエンコードする。

例

```
FCF vs ハマーズ
```

↓

```
FCF%20vs%20ハマーズ
```

---

# 27.8 Streamlit UI

抽出された試合ごとに  
カレンダー登録リンクを生成する。

例

```
[カレンダー登録]
FCF vs ハマーズ
```

---

# 27.9 複数試合対応

試合ごとにリンク生成

例

|試合|登録|
|---|---|
FCF vs ハマーズ|登録|
新潟四十雀60 vs NFC60|登録|
PRSフューチャーズ vs SF長岡60|登録|

---

# 27.10 出力データ

リンク生成時に使用するデータ

```
date
time
age_group
home
away
referee
assistant
location
```

---

# 27.11 完成動作

```
PDFアップロード
↓
試合抽出
↓
自チーム試合フィルタ
↓
試合表示
↓
Googleカレンダー登録リンク生成
```

---

# 27.12 完成例

カレンダー登録後

```
タイトル

FCF vs ハマーズ
```

カレンダーを見たときに

```
どの試合か一目で分かる
```

# 28 チーム名解析修正

チーム名にスペースを含む場合があるため  
単純なスペース分割による解析は禁止する。

例

```
FC revoltijo
```

---

# 28.1 試合行解析方法

試合行は以下形式

```
No 時間 H × A 主審 副審
```

例

```
6 14:20 FCF × ハマーズ FC revoltijo ナオネスターズ上越40
```

---

# 28.2 解析手順

① No と 時間を取得

② 残り文字列を取得

③ `×` を基準に分割

---

# 28.3 解析例

入力

```
6 14:20 FCF × ハマーズ FC revoltijo ナオネスターズ上越40
```

処理

```
No = 6
time = 14:20

rest =
FCF × ハマーズ FC revoltijo ナオネスターズ上越40
```

---

### ホーム / アウェイ分割

```
home_part, rest_part = rest.split("×")
```

結果

```
home = "FCF"
rest_part = "ハマーズ FC revoltijo ナオネスターズ上越40"
```

---

### 審判分割

後ろ2チームが審判

```
tokens = rest_part.split()
```

例

```
["ハマーズ", "FC", "revoltijo", "ナオネスターズ上越40"]
```

---

### 審判

```
assistant = tokens[-1]
referee = " ".join(tokens[-3:-1])
```

結果

```
referee = FC revoltijo
assistant = ナオネスターズ上越40
```

---

### アウェイ

```
away = " ".join(tokens[:-3])
```

結果

```
away = ハマーズ
```

---

# 28.4 最終結果

```
No: 6
time: 14:20
home: FCF
away: ハマーズ
referee: FC revoltijo
assistant: ナオネスターズ上越40
```

---

# 28.5 対応できるケース

この方式で以下すべて対応可能

```
FC revoltijo
JS CLASSIC
M.sea新潟
新潟四十雀シニア
```

---

# 28.6 解析優先順位

```
1 × でチーム区切り
2 後ろ2チームを審判
3 残りをアウェイ
```

# 追加仕様：チーム名例外処理（FC revoltijo対応）

## 29 目的

チーム名

```
FC revoltijo
```

がスペース分割によって

```
FC
revoltijo
```

と分割されてしまう問題を修正する。

また、この分割により  
審判・副審の位置がずれる問題にも対応する。

---

# 29.1 基本方針

基本の解析ロジックは変更しない。

```
No 時間 H × A 主審 副審
```

スペース分割で解析する。

ただし  
特定チーム名のみ例外処理を行う。

---

# 29.2 例外チーム辞書

例外チームを辞書として定義する。

```
SPECIAL_TEAM_NAMES = [
    "FC revoltijo"
]
```

---

# 29.3 前処理

行解析の前に  
例外チーム名を **結合表記へ変換**する。

例

```
FC revoltijo
```

↓

```
FC_revoltijo
```

処理

```
line = line.replace("FC revoltijo", "FC_revoltijo")
```

---

# 29.4 トークン解析

その後通常のスペース分割を行う。

```
tokens = line.split()
```

例

```
6 14:20 FCF × ハマーズ FC_revoltijo ナオネスターズ上越40
```

結果

```
[
"6",
"14:20",
"FCF",
"×",
"ハマーズ",
"FC_revoltijo",
"ナオネスターズ上越40"
]
```

---

# 29.5 チーム名復元

解析後  
元のチーム名に戻す。

```
name.replace("_", " ")
```

例

```
FC_revoltijo
```

↓

```
FC revoltijo
```

---

# 29.6 解析結果

例

入力

```
6 14:20 FCF × ハマーズ FC revoltijo ナオネスターズ上越40
```

抽出結果

```
No: 6
time: 14:20
home: FCF
away: ハマーズ
referee: FC revoltijo
assistant: ナオネスターズ上越40
```

---

# 29.7 後続データの補正

スペース分割のズレにより  
審判・副審の位置が崩れていた可能性がある。

そのため以下ルールを適用する。

```
tokens[-2] = referee
tokens[-1] = assistant
```

---

# 29.8 安全処理

試合行トークン数が不足する場合

```
len(tokens) < 7
```

ログ出力

```
試合解析エラー
```

ログ保存

```
logs/parser_error.log
```

---

# 29.9 将来拡張

他にもスペースを含むチーム名が発生した場合  
辞書に追加する。

例

```
SPECIAL_TEAM_NAMES = [
"FC revoltijo",
"fc ziarllo"
]
```

---

# 29.10 完成動作

```
PDF解析
↓
例外チーム名置換
↓
スペース分割
↓
試合解析
↓
チーム名復元
```

これにより

```
FC revoltijo
```

を正しく解析できる。

# 追加仕様：開催日・会場の取得

## 30 目的

試合データに **会場情報** を追加する。

PDF内には試合ブロックの前に  
開催日と会場が記載されている。

例

```
開催日： 4月5日 会場：潟東サルビアサッカー場
```

この情報を取得し  
以降の試合データに紐付ける。

---

# 30.1 取得対象

取得する情報

|項目|例|
|---|---|
date|4月5日|
location|潟東サルビアサッカー場|

---

# 30.2 ヘッダー行判定

以下の文字列を含む行を検出する。

```
開催日：
```

かつ

```
会場：
```

---

# 30.3 正規表現

```
開催日：\s*(\d+月\d+日)\s*会場：(.+)
```

取得

```
group1 = 日付
group2 = 会場
```

例

入力

```
開催日： 4月5日 会場：潟東サルビアサッカー場
```

抽出

```
date = 4月5日
location = 潟東サルビアサッカー場
```

---

# 30.4 内部状態

現在の試合グループ情報として保存

```
current_date
current_location
```

例

```
current_date = "2026-04-05"
current_location = "潟東サルビアサッカー場"
```

---

# 30.5 試合データへの適用

試合行解析時に  
現在の情報を追加する。

```
match = {

date: current_date,
location: current_location,

age_group: age_group,
no: no,
time: time,

home: home,
away: away,

referee: referee,
assistant: assistant

}
```

---

# 30.6 複数会場対応

PDFでは途中で会場が変わる場合がある。

例

```
開催日： 4月5日 会場：潟東サルビアサッカー場
(試合データ)

開催日： 4月12日 会場：アルビレッジ
(試合データ)
```

その場合

```
current_date
current_location
```

を更新する。

---

# 30.7 日付フォーマット

抽出日付

```
4月5日
```

を

```
YYYY-MM-DD
```

へ変換する。

例

```
2026-04-05
```

※年はPDFタイトルから取得

```
2026年 新潟県シニアサッカー日程表
```

---

# 30.8 Googleカレンダーへの反映

会場は

```
location
```

として登録する。

例

```
潟東サルビアサッカー場
```

---

# 30.9 CSV出力

CSVに以下項目を追加

```
date
location
age_group
no
time
home
away
referee
assistant
```

例

```
2026-04-05,潟東サルビアサッカー場,60,1,09:30,新潟四十雀60,NFC60,PRSフューチャーズ,SF長岡60
```

---

# 30.10 デバッグ表示

開発者モードON時

表示

```
current_date
current_location
```

例

```
DATE = 2026-04-05
LOCATION = 潟東サルビアサッカー場
```

---

# 30.11 完成動作

```
PDF読み込み
↓
開催日行検出
↓
current_date 更新

会場行検出
↓
current_location 更新

試合行
↓
試合データ生成
↓
date/location付与
```

---

# 30.12 最終データ構造

```
match = {

date: "2026-04-05",
location: "潟東サルビアサッカー場",

age_group: "60",
no: 1,
time: "9:30",

home: "新潟四十雀60",
away: "NFC60",

referee: "PRSフューチャーズ",
assistant: "SF長岡60"

}
```