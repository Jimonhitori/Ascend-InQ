"""Ascend InQ — League of Legends の試合を録画して振り返るツール.

  python review.py                    直近5試合を取得してレポート作成（メインアカウント）
  python review.py -n 10 --id "Name#TAG"
  python review.py report <match_id>  保存済みデータからレポートだけ作り直す（APIを使わない）
  python review.py view [match_id]    動画＋シークバー＋解説のビューアを開く
  python review.py record [--open]    試合を自動録画（常駐）→ 試合後にビューア作成
  python review.py clip [match_id|latest] [--video 録画ファイル] [--offset 秒]
"""
import argparse
import os
import sys
from pathlib import Path

from ascendinq import clips, config, fetch, pipeline, report
from ascendinq.lcu import ClientNotRunning
from ascendinq.riot import RiotAPIError


puuid_for, build, viewer_path = pipeline.puuid_for, pipeline.build, pipeline.viewer_path


def cmd_fetch(args):
    if args.id and args.id != config.riot_id():
        os.environ["RIOT_ID"] = args.id
    src = "Riot API" if config.settings()["source"] == "api" else "LoL クライアント"
    print(f"{src} から直近{args.n}試合を確認中…")
    riot_id, puuid, ids, new = pipeline.import_recent(args.n)
    if not ids:
        print("試合が見つかりませんでした。")
        return
    print(f"新しく取得: {len(new)} 試合")
    analyses = []
    for mid in ids:
        a, path = build(mid, puuid)
        analyses.append(a)
    idx = report.write_index(analyses)
    a = analyses[0]
    print("\n=== 最新の試合 ===")
    print(report._header(a)[2], "/", report._header(a)[1])
    print("次の試合で意識すること:", a["focus"])
    for i, iss in enumerate(a["issues"][:3], 1):
        print(f"  {i}. {iss['title']}")
    print(f"\nビューア: {viewer_path(a['match_id'])}")
    print(f"一覧    : {idx}")
    if args.open:
        os.startfile(viewer_path(a["match_id"]))


def cmd_report(args):
    puuid = puuid_for(args.id)
    a, path = build(args.match_id, puuid)
    print(f"レポート: {path}")


def cmd_view(args):
    puuid = puuid_for(args.id)
    ids = fetch.cached_match_ids()
    mid = ids[0] if args.match_id == "latest" and ids else args.match_id
    a, _ = build(mid, puuid, args.video, args.offset)
    path = viewer_path(mid)
    print(f"ビューア: {path}")
    os.startfile(path)


def cmd_record(args):
    from ascendinq import recorder

    def after_game(video, info):
        a, path = pipeline.review_after_game(video, info, args.id)
        if a:
            print(f"  次の試合で意識すること: {a['focus']}")
            print(f"  ビューア: {path}")
            if args.open:
                os.startfile(path)

    recorder.run(None if args.no_review else after_game)


def cmd_clip(args):
    puuid = puuid_for(args.id)
    ids = fetch.cached_match_ids()
    mid = ids[0] if args.match_id == "latest" and ids else args.match_id
    a, _ = build(mid, puuid)
    if not a["deaths"]:
        print("この試合はデスがないので切り出すものがありません。")
        return
    video = args.video or clips.find_video(a["game_start_ms"])
    if not video:
        sys.exit("この試合の録画が見つかりません。.env の VIDEO_DIR を設定するか、--video で録画ファイルを指定してください。")
    n = clips.cut_deaths(a, video, args.offset)
    path = report.write(a)  # re-render so the stills appear in the report
    print(f"{n} 件切り出しました。レポート: {path}")


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--id", default=config.riot_id(), help="Riot ID（例: Name#JP1）。省略時は .env の RIOT_ID")
    ap = argparse.ArgumentParser(description="Ascend InQ — LoL の試合を録画して振り返るツール")
    sub = ap.add_subparsers(dest="cmd")
    f = sub.add_parser("fetch", parents=[common], help="直近の試合を取得してレポート作成（既定）")
    f.add_argument("-n", type=int, default=5, help="取得する試合数")
    f.add_argument("--open", action="store_true", help="最新試合のビューアをブラウザで開く")
    v = sub.add_parser("view", parents=[common], help="動画＋解説のビューアをブラウザで開く")
    v.add_argument("match_id", nargs="?", default="latest")
    v.add_argument("--video", type=Path, help="録画ファイル（省略時は自動で探す）")
    v.add_argument("--offset", type=float, help="ゲーム内0:00が動画の何秒目か")
    r = sub.add_parser("report", parents=[common], help="保存済みデータからレポートを作り直す")
    r.add_argument("match_id")
    rc = sub.add_parser("record", parents=[common], help="試合を自動で録画（常駐）")
    rc.add_argument("--open", action="store_true", help="試合後にビューアを自動で開く")
    rc.add_argument("--no-review", action="store_true", help="録画だけして、試合データの取得はしない")
    c = sub.add_parser("clip", parents=[common], help="録画からデス場面を切り出す")
    c.add_argument("match_id", nargs="?", default="latest")
    c.add_argument("--video", type=Path)
    c.add_argument("--offset", type=float, help="ゲーム内0:00が動画の何秒目か（自動推定がずれる時に指定）")
    argv = sys.argv[1:]
    if not argv or argv[0] not in ("fetch", "report", "clip", "view", "record", "-h", "--help"):
        argv = ["fetch", *argv]
    args = ap.parse_args(argv)
    try:
        {"fetch": cmd_fetch, "report": cmd_report, "clip": cmd_clip, "view": cmd_view, "record": cmd_record}[args.cmd](args)
    except (config.ConfigError, RiotAPIError, ClientNotRunning, FileNotFoundError, ValueError, RuntimeError) as e:
        sys.exit(f"エラー: {e}")
    except KeyboardInterrupt:
        print("終了しました。")


if __name__ == "__main__":
    main()
