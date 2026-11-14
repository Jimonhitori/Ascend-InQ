"""Classify each death into a cause and write one concrete action for it.

Every death gets exactly one *primary* cause (what went wrong first) plus
optional *impact* notes (what the death cost). Causes use only facts the
analyzer measured; when live data from the recording is present (my HP and
unspent gold, enemies alive) the verdicts get sharper.

Rules are versioned so viewer feedback ("合ってる / 違う") can be tied to the
rule set that produced it.
"""


def mmss(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"

RULES_VERSION = 1

# priority order: the first matching cause is the primary one
PRIMARY_ORDER = ["gank", "jg_duel", "low_hp", "outnumbered", "bad_trade", "died_first", "stayed_lost",
                 "overextend", "traded", "skirmish", "unknown"]

GROUP_TITLE = {
    "gank": "序盤の敵JGのガンクで倒されている",
    "jg_duel": "序盤に敵JGとの戦いで倒されている",
    "low_hp": "体力が低いまま戦って倒されている",
    "bad_trade": "対面との1v1で倒されている",
    "outnumbered": "人数不利の場所で捕まっている",
    "overextend": "味方から離れて敵側で倒されている",
    "died_first": "集団戦・小競り合いで最初に倒されている",
    "stayed_lost": "負けている戦いから引けずに倒されている",
    "traded": "相打ち・交換でのデス（大きな問題なし）",
    "skirmish": "小競り合いに負けて倒されている",
    "unknown": "原因がはっきりしないデスがある",
}
BASE_WEIGHT = {"gank": 3, "jg_duel": 3, "low_hp": 2.5, "bad_trade": 2.5, "outnumbered": 2.5,
               "overextend": 2, "died_first": 2.5, "stayed_lost": 1.5, "traded": 0.3, "skirmish": 1.5, "unknown": 1}

ENEMY_SIDE = ("敵側", "敵陣")
DANGER = ("リバー", "敵陣ジャングル", "敵側")


def _pct(x):
    return f"{round(x * 100)}%"


def classify(d: dict, role: str, enemy_jg: str | None) -> dict:
    """Return {"primary": cause, "impacts": [...], "weight": float}. cause = {key, label, why, action}."""
    early = d["t"] < 15 * 60
    allies = len(d["allies_near"])
    n = d["n_enemies"]
    hp = d.get("hp_before")            # 0..1 or None (live data only)
    alive = d.get("enemies_alive")     # 0..5 or None (live data only)
    pushed = any(k in d["zone"] for k in ENEMY_SIDE)
    wards = d.get("my_wards_3min")
    causes = {}

    if d["jg_involved"] and early:
        where = f"20秒前の敵JGは{d['ejg_zone_20s']}" if d.get("ejg_zone_20s") not in (None, "?") else ""
        if role == "JUNGLE":
            causes["jg_duel"] = {
                "label": "敵JGとの戦いに負けた",
                "why": f"敵JG（{enemy_jg or '?'}）と{d['zone']}で戦って倒された（レベル {d['level']}）。",
                "action": "敵JGの初手ルートから位置を予想し、相手の方がレベル・体力で有利な時は競らずに反対側を狩る。",
            }
        else:
            why = f"敵JG（{enemy_jg or '?'}）に{d['zone']}で捕まった。" + (f"{where}。" if where else "")
            if pushed:
                why += "敵側に押し込んだ位置だった。"
                action = "敵JGの位置が分からない時は、ウェーブを押し切ったらすぐ自陣側へ下がる。"
            else:
                action = "敵JGが来られる距離にいる時（最後に見えてから45秒以内）は、前に出ずにフラッシュを温存する。"
            causes["gank"] = {"label": "敵JGのガンク", "why": why, "action": action}

    if hp is not None and hp <= 0.35:
        causes["low_hp"] = {
            "label": "体力が低いまま残った",
            "why": f"倒される約10秒前の体力が{_pct(hp)}しかなかった。",
            "action": "体力が4割を切ったら、ウェーブを処理して帰還する。戦うのは体力が戻ってから。",
        }

    if n == 1:
        lvl = d["level"]
        olvl = d.get("killer_level") or (d.get("opp_level") if d["killer_is_opp"] else None)
        gd = d.get("killer_gold_diff") if d.get("killer_gold_diff") is not None else d.get("lane_gold_diff")
        if olvl and olvl > lvl:
            why, action = (f"レベルで負けている状態（{lvl} vs {olvl}）で1v1をした。",
                           "相手の方がレベルが高い時は戦わない。特にレベル2・3・6の差がつく瞬間に注意。")
        elif gd is not None and gd < -300:
            why, action = (f"ゴールドで負けている状態（{gd:+}）で1v1をした。",
                           "アイテム差がある時は、タワー下でCSを取って差が縮まるのを待つ。")
        else:
            why, action = ("レベルもゴールドもほぼ互角の1v1で負けた。",
                           "仕掛ける前に相手の主要スキルのクールダウンを確認し、外した直後だけ戦う。")
        who = "対面" if d["killer_is_opp"] else d["killer"]
        causes["bad_trade"] = {"label": f"{who}との1v1に負けた", "why": f"{d['killer']}に1v1で倒された。" + why, "action": action}

    if n >= 2 and n >= allies + 2:
        extra = f"（その時生きていた敵 {alive}人）" if alive is not None else ""
        causes["outnumbered"] = {
            "label": "人数不利で捕まった",
            "why": f"敵{n}人に対して、近くの味方は{allies}人だった{extra}。",
            "action": "ミニマップに映っていない敵の人数を数え、2人以上見えていない時は前に出ない。",
        }

    if allies == 0 and any(k in d["zone"] for k in DANGER):
        why = f"味方がいない{d['zone']}で倒された。"
        if wards == 0:
            why += "直前3分にワードも置いていなかった。"
        causes["overextend"] = {
            "label": "味方から離れて前に出た",
            "why": why,
            "action": "リバーや敵陣に1人で入る前に、ワードかスイーパーを使い、敵JGとMIDの位置を確認する。",
        }

    fight = d.get("fight") or {}
    if allies >= 1 and n >= 2:  # skirmish / teamfight with allies around
        if fight.get("enemies_dead", 0) >= max(1, fight.get("allies_dead_before", 0) + 1):
            causes["traded"] = {
                "label": "相打ち・交換",
                "why": f"この戦いで敵も{fight['enemies_dead']}人倒れている（交換は成立）。",
                "action": "大きな問題なし。余裕があれば、倒される前に一歩下がれたかだけ確認する。",
            }
        elif fight.get("first"):
            causes["died_first"] = {
                "label": "戦いで最初に倒された",
                "why": f"味方{allies}人がいる戦い（敵{n}人）で、誰よりも先に倒された。",
                "action": "戦いが始まる前は味方の後ろか横に立ち、敵の突っ込み役（イニシエーター）のスキルが外れてから前に出る。",
            }
        elif fight.get("allies_dead_before", 0) >= 2:
            causes["stayed_lost"] = {
                "label": "負け戦から引けなかった",
                "why": f"味方が先に{fight['allies_dead_before']}人倒れた後も戦場に残っていた。",
                "action": "味方が2人倒れたら、その戦いは捨てて安全な方向へ下がる。",
            }
        else:
            causes["skirmish"] = {
                "label": "小競り合いに負けた",
                "why": f"味方{allies}人・敵{n}人の小競り合いで倒された。",
                "action": "戦う前に、敵の主要スキル（特にCC）が使われたかを確認してから仕掛ける。",
            }

    if not causes:
        causes["unknown"] = {
            "label": "原因不明",
            "why": "データからは原因を特定できなかった。",
            "action": "動画で、倒される5〜10秒前に前に出た理由と逃げ道を確認する。",
        }

    key = next(k for k in PRIMARY_ORDER if k in causes)
    primary = dict(causes[key], key=key)
    secondary = [dict(c, key=k) for k, c in causes.items() if k != key and k not in ("traded", "unknown")]

    impacts = []
    weight = BASE_WEIGHT[key] + (1 if early else 0)
    if d["lost_after"]:
        impacts.append({"key": "objective", "why": f"このデス中に{'・'.join(d['lost_after'])}を取られた。",
                        "action": "オブジェクト湧きの1分前からは無理をしない。生きていること自体が準備。"})
        weight += 2 * len(d["lost_after"])
    gold = d.get("gold_unspent")
    if gold is not None and gold >= 1300:
        impacts.append({"key": "late_back", "why": f"{gold}ゴールドを使わないまま倒された。",
                        "action": "1300ゴールド前後たまったら、次のウェーブを押して帰還する。"})
        weight += 1
    if d.get("bounty", 0) >= 500:
        impacts.append({"key": "bounty", "why": f"賞金{d['bounty']}ゴールドを敵に渡した。", "action": ""})
        weight += 1
    return {"primary": primary, "secondary": secondary, "impacts": impacts, "weight": weight}


def group_issues(deaths: list) -> list:
    """Aggregate classified deaths into issues (one per primary cause)."""
    groups = {}
    for d in deaths:
        c = d.get("cause")
        if not c:
            continue
        groups.setdefault(c["primary"]["key"], []).append(d)
    issues = []
    for key, ds in groups.items():
        if (key == "unknown" and len(ds) < 2) or key == "traded":
            continue
        detail = " / ".join(f"{mmss(d['t'])} {d['cause']['primary']['why']}" for d in ds)
        actions = [d["cause"]["primary"]["action"] for d in ds]
        issues.append({"score": sum(d["cause"]["weight"] for d in ds), "title": GROUP_TITLE[key],
                       "detail": detail, "focus": max(set(actions), key=actions.count), "cause": key})
    lost = [d for d in deaths if d["lost_after"]]
    if lost:
        issues.append({"score": 3 * len(lost), "title": "デスの直後にオブジェクトを取られている",
                       "detail": "、".join(f"{mmss(d['t'])}→{'/'.join(d['lost_after'])}" for d in lost),
                       "focus": "オブジェクト湧きの1分前からは無理なトレードや単独行動をしない。生きていること自体がオブジェクトの準備。",
                       "cause": "objective"})
    rich = [d for d in deaths if (d.get("gold_unspent") or 0) >= 1300]
    if len(rich) >= 2:
        issues.append({"score": 1.5 * len(rich), "title": "ゴールドを持ったまま倒されている",
                       "detail": "、".join(f"{mmss(d['t'])}（{d['gold_unspent']}G）" for d in rich),
                       "focus": "1300ゴールド前後たまったら、次のウェーブを押して帰還する。", "cause": "late_back"})
    return issues
