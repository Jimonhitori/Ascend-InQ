# Ascend InQ

**Ascend in queue** — キューに潜るたびに上がっていくための、League of Legends 振り返りツール。

ソロランクを、試合後に **動画＋シークバー＋場面ごとの解説** で振り返るツール。

- 試合を自動で録画（GPUエンコードで超軽量。CPU使用率は全体の0.2%程度）
- 試合後に Riot API から試合データを取り、デス・オブジェクト・レーン差などを分析
- ビューアで、シークバーの重要な場面をクリック → その場面の映像と「どうするべきだったか」が出る
- 録画が無くても、APIの位置データからミニマップ上で10人の動きを再生できる

> 試合中に動くのは「録画」と「試合が終わったかの確認（数秒に1回、自分のPC内への小さな問い合わせ）」だけです。分析は試合後に行います。

## 必要なもの
- Windows 10/11
- Python 3.10 以上
- ffmpeg（`winget install Gyan.FFmpeg` で入ります）
- 録画する場合: NVIDIA / AMD / Intel のGPU（ハードウェアエンコーダー）
- Riot API キー（https://developer.riotgames.com でログインして発行）

## セットアップ
```
git clone https://github.com/Jimonhitori/Ascend-InQ.git
cd Ascend-InQ
pip install -r requirements.txt
copy .env.example .env
notepad .env
```
`.env` に `RIOT_API_KEY` と自分の `RIOT_ID`（例: `Name#JP1`）を書きます。
開発用キーは24時間で失効するので、失効したら再発行して貼り直してください。

## 使い方
### いちばん簡単: 自動録画＋自動振り返り
`start_recorder.bat` をダブルクリックして、そのまま LoL をプレイ。
試合が始まると録画が始まり、終わるとAPIから試合データを取ってビューアが開きます。
（Outplayed / OBS など他の録画ソフトは止めておいてください）

### コマンド
```
python review.py record --open        # 自動録画（常駐）。試合後にビューアを開く
python review.py                      # 直近5試合を取得してレポート/ビューア作成
python review.py --open               # 同上＋最新試合のビューアを開く
python review.py view [試合ID]         # ビューアを開く（省略時は最新）
python review.py -n 10 --id "Name#TAG"
python review.py report 試合ID         # 保存済みデータから作り直し（APIを使わない）
python review.py clip [試合ID]         # デス場面を短い動画と静止画に切り出し（clips/）
```
`reports/index.html` に試合一覧と「何試合も続けて出ている改善点」がまとまります。

### ビューアの操作
- シークバーのアイコン / 右の一覧をクリック → その場面の少し前に飛んで解説を表示
- Space 再生/停止、←→ 5秒、N / P 次/前の重要場面
- 他のソフトで録った動画は「🎬 録画を開く」で読み込めます。時刻がずれたら下の「同期」で調整（試合ごとに記憶）
- Outplayed / OBS の録画フォルダ（`ビデオ\Overwolf\Outplayed` など）も自動で探します

## 録画の設定（`.env`）
| 項目 | 既定 | 説明 |
|---|---|---|
| `RECORD_MONITOR` | 0 | 録画するモニター |
| `RECORD_FPS` | 30 | フレームレート |
| `RECORD_QUALITY` | 30 | 小さいほど高画質（ファイルも大きい） |
| `RECORD_KEEP` | 30 | `recordings/` に残す録画数。古いものから自動削除（0で削除しない） |

録画は画面全体（音声なし）です。1試合あたり 1GB 前後になります。

## わかること・わからないこと
- **わかる（マクロ）**: デスの場所・人数・敵JGの位置、オブジェクトへの参加、CS/ゴールド/経験値差、アイテム完成時刻、ローム
- **わからない（ミクロ）**: スキルの当て合い、トレード、ウェーブの細かい状態 → ここは映像で確認
- 位置は1分ごとのデータとイベントからの推定。ワードの置き場所は Riot API に無いため、置いた数で代用しています

## 免責
Ascend InQ isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

## ライセンス
MIT License（[LICENSE](LICENSE)）
