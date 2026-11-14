# Ascend InQ

League of Legends のソロランク試合を録画し、試合後に「その場面でどうするべきだったか」を解説付きで振り返るツール。
MIT License で公開している OSS。個人用の情報は `CLAUDE.local.md`（git管理外）に書く。

## 方針
- **試合中は可能な限り軽く**: 試合中に動くのは GPU エンコードの録画と、Live Client Data API（127.0.0.1:2999）への数秒おきの問い合わせだけ。分析・API取得は試合後。
- Python 3.10+、依存は requests / python-dotenv / pystray / pillow と外部の ffmpeg に抑える。ビューアは静的HTML（サーバー不要・外部ライブラリなし）
- ユーザー向けの文言・README・コメントは日本語
- 個人情報（Riot ID・APIキー・録画）をリポジトリに入れない

## 構成
- `app.py` → `ascendinq/tray.py` — タスクトレイアプリ（.exe の本体）。`build.bat` で PyInstaller ビルド、`--selftest` で動作確認
- `review.py` — CLI（fetch / view / record / report / clip）
- `ascendinq/pipeline.py` — CLI とトレイアプリ共通の処理（取得→分析→ビューア作成、試合後の自動レビュー）
- `ascendinq/riot.py` — Riot API クライアント（レート制限 20/1s・100/2min、429 は Retry-After、401/403 は失効メッセージ）
- `ascendinq/fetch.py` — Riot ID → PUUID → ソロランク（queue=420）の試合とタイムラインを `data/` に保存
- `ascendinq/analyze.py` — 1試合の分析（デス・レーン差・オブジェクト・アイテム・ローム）と改善点ルール
- `ascendinq/report.py` — `reports/` に Markdown / HTML / 一覧
- `ascendinq/viewer.py` + `viewer_template.html` — 動画＋ミニマップ＋シークバー＋場面解説のビューア
- `ascendinq/recorder.py` — 試合検知して ddagrab + NVENC/AMF/QSV で録画、終了後に自動レビュー
- `ascendinq/clips.py` — 録画からの場面切り出し、録画と試合の時刻対応

## Riot API
- キーは `.env` の `RIOT_API_KEY`。コード・ログ・チャットに出さない
- ルーティング: Account-V1 / Match-V5 は `REGION`（既定 asia）、プラットフォームは `PLATFORM`（既定 jp1）
- Riot API にワードの設置位置は無い。位置は1分ごとのフレーム＋イベントからの推定
