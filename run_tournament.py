"""
Full round-robin tournament runner.
Runs every 1v1 combination of bots and saves detailed stats to statistics/.
"""

import os
import subprocess
import json
import re
import itertools
from datetime import datetime

MAIN_BOTS = [
    "rishabh_bot",
    "SaptiBot",
    "madhav_claudeide_bot",
]

BOTS = [
    "rishabh_bot",
    "SaptiBot",
    "madhav_claudeide_bot",
    "all_in_bot",
    "heuristic_bot",
    "aggresive_botr",
    "tight_bot",
    "check_call_bot",
    "maniac_bot",
    "passive_bot",
    "station_bot",
    "tag_bot",
]

RESULTS_DIR      = "statistics"
MAIN_DIR         = "statistics/main"
OTHER_DIR        = "statistics/other"
CONFIG_FILE      = "config.py"
ENGINE_SCRIPT    = "engine.py"

os.makedirs(MAIN_DIR,  exist_ok=True)
os.makedirs(OTHER_DIR, exist_ok=True)
os.makedirs("statistics/tmp", exist_ok=True)


def write_config(bot1, bot2):
    config = f"""# PARAMETERS TO CONTROL THE BEHAVIOR OF THE GAME ENGINE
# DO NOT REMOVE OR RENAME THIS FILE
PLAYER_1_NAME = "{bot1}"
PLAYER_1_PATH = "./{bot1}"
PLAYER_2_NAME = "{bot2}"
PLAYER_2_PATH = "./{bot2}"
GAME_LOG_FILENAME = "gamelog"
RESULTS_DIR = "./statistics/tmp"
PLAYER_LOG_SIZE_LIMIT = 524288
ENFORCE_GAME_CLOCK = True
STARTING_GAME_CLOCK = 180.0
BUILD_TIMEOUT = 10.0
CONNECT_TIMEOUT = 10.0
NUM_ROUNDS = 1000
STARTING_STACK = 400
BIG_BLIND = 5
SMALL_BLIND = 2
PLAYER_TIMEOUT = 180
"""
    with open(CONFIG_FILE, "w") as f:
        f.write(config)


def parse_gamelog(logfile, bot1, bot2):
    """Parse engine gamelog and extract per-hand results."""
    stats = {
        "bot1": bot1, "bot2": bot2,
        "bot1_total": 0, "bot2_total": 0,
        "hands_played": 0,
        "bot1_wins": 0, "bot2_wins": 0, "ties": 0,
        "bot1_biggest_win": 0, "bot2_biggest_win": 0,
        "bot1_redraw_count": 0, "bot2_redraw_count": 0,
        "hand_deltas": [],
    }

    if not os.path.exists(logfile):
        return stats

    with open(logfile) as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        # awarded lines: "botname awarded 42"
        m = re.match(rf"^{re.escape(bot1)} awarded (-?\d+)$", line)
        if m:
            delta = int(m.group(1))
            stats["bot1_total"] += delta
            stats["hand_deltas"].append(delta)
            stats["hands_played"] += 1
            if delta > 0:
                stats["bot1_wins"] += 1
                stats["bot1_biggest_win"] = max(stats["bot1_biggest_win"], delta)
            elif delta < 0:
                stats["bot2_wins"] += 1
                stats["bot2_biggest_win"] = max(stats["bot2_biggest_win"], -delta)
            else:
                stats["ties"] += 1

        # redraw lines
        if "redraws" in line.lower() or "redraw" in line.lower():
            if bot1.lower() in line.lower():
                stats["bot1_redraw_count"] += 1
            elif bot2.lower() in line.lower():
                stats["bot2_redraw_count"] += 1

    stats["bot2_total"] = -stats["bot1_total"]
    stats["winner"] = bot1 if stats["bot1_total"] > stats["bot2_total"] else (
        bot2 if stats["bot2_total"] > stats["bot1_total"] else "TIE"
    )

    # Compute streaks
    best_streak = 0; cur_streak = 0
    worst_streak = 0; cur_loss = 0
    for d in stats["hand_deltas"]:
        if d > 0:
            cur_streak += 1; cur_loss = 0
            best_streak = max(best_streak, cur_streak)
        elif d < 0:
            cur_loss += 1; cur_streak = 0
            worst_streak = max(worst_streak, cur_loss)
        else:
            cur_streak = 0; cur_loss = 0
    stats["bot1_best_win_streak"]  = best_streak
    stats["bot1_worst_loss_streak"] = worst_streak

    return stats


def run_match(bot1, bot2, out_dir):
    print(f"  Running: {bot1} vs {bot2} ...", end=" ", flush=True)
    write_config(bot1, bot2)

    result = subprocess.run(
        ["python3", ENGINE_SCRIPT],
        capture_output=True, text=True, timeout=600
    )

    logfile = "statistics/tmp/gamelog.txt"
    stats   = parse_gamelog(logfile, bot1, bot2)

    # Save raw engine output
    with open(os.path.join(out_dir, f"{bot1}_vs_{bot2}_engine.log"), "w") as f:
        f.write(result.stdout)
        if result.stderr:
            f.write("\n--- STDERR ---\n")
            f.write(result.stderr)

    # Save gamelog
    if os.path.exists(logfile):
        import shutil
        shutil.copy(logfile, os.path.join(out_dir, f"{bot1}_vs_{bot2}_gamelog.txt"))

    winner_str = f"WINNER: {stats['winner']}"
    print(f"{stats['bot1_total']:+d} chips  →  {winner_str}")
    return stats


def save_matchup_report(stats, out_dir):
    bot1, bot2 = stats["bot1"], stats["bot2"]
    path = os.path.join(out_dir, f"{bot1}_vs_{bot2}_report.txt")
    hands = stats["hands_played"] or 1
    with open(path, "w") as f:
        f.write(f"{'='*60}\n")
        f.write(f"  MATCHUP: {bot1}  vs  {bot2}\n")
        f.write(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'='*60}\n\n")
        f.write(f"  Hands played      : {stats['hands_played']}\n")
        f.write(f"  Winner            : {stats['winner']}\n\n")
        f.write(f"  {bot1:<22} | {bot2}\n")
        f.write(f"  {'-'*50}\n")
        f.write(f"  Total chips       : {stats['bot1_total']:+d}  |  {stats['bot2_total']:+d}\n")
        f.write(f"  Hands won         : {stats['bot1_wins']}  |  {stats['bot2_wins']}  (ties: {stats['ties']})\n")
        f.write(f"  Win rate          : {stats['bot1_wins']/hands*100:.1f}%  |  {stats['bot2_wins']/hands*100:.1f}%\n")
        f.write(f"  Avg chips/hand    : {stats['bot1_total']/hands:+.2f}  |  {stats['bot2_total']/hands:+.2f}\n")
        f.write(f"  Biggest single win: {stats['bot1_biggest_win']}  |  {stats['bot2_biggest_win']}\n")
        f.write(f"  Best win streak   : {stats['bot1_best_win_streak']} hands\n")
        f.write(f"  Worst loss streak : {stats['bot1_worst_loss_streak']} hands\n")
        if stats['bot1_redraw_count'] or stats['bot2_redraw_count']:
            f.write(f"  Redraws used      : {stats['bot1_redraw_count']}  |  {stats['bot2_redraw_count']}\n")
        f.write(f"\n")


def save_main_summary(main_stats):
    """Detailed summary for the 3 main bots vs all opponents."""
    bots_seen = set()
    for s in main_stats:
        bots_seen.add(s["bot1"]); bots_seen.add(s["bot2"])
    all_bots = list(bots_seen)

    records = {b: {"wins": 0, "losses": 0, "ties": 0, "total_chips": 0,
                   "matchups": [], "avg_chips": 0, "win_rate": 0.0} for b in all_bots}

    for s in main_stats:
        b1, b2 = s["bot1"], s["bot2"]
        hands = s["hands_played"] or 1
        records[b1]["total_chips"] += s["bot1_total"]
        records[b2]["total_chips"] += s["bot2_total"]
        r1 = "W" if s["winner"] == b1 else ("T" if s["winner"] == "TIE" else "L")
        r2 = "W" if s["winner"] == b2 else ("T" if s["winner"] == "TIE" else "L")
        records[b1]["matchups"].append({
            "opponent": b2, "result": r1,
            "chips": s["bot1_total"], "win_rate": s["bot1_wins"] / hands * 100,
            "avg_per_hand": s["bot1_total"] / hands,
            "biggest_win": s["bot1_biggest_win"],
        })
        records[b2]["matchups"].append({
            "opponent": b1, "result": r2,
            "chips": s["bot2_total"], "win_rate": s["bot2_wins"] / hands * 100,
            "avg_per_hand": s["bot2_total"] / hands,
            "biggest_win": s["bot2_biggest_win"],
        })
        if s["winner"] == b1:
            records[b1]["wins"] += 1; records[b2]["losses"] += 1
        elif s["winner"] == b2:
            records[b2]["wins"] += 1; records[b1]["losses"] += 1
        else:
            records[b1]["ties"] += 1; records[b2]["ties"] += 1

    # Focus ranking on main bots only
    main_ranked = sorted(
        [(b, records[b]) for b in MAIN_BOTS if b in records],
        key=lambda x: (x[1]["wins"], x[1]["total_chips"]), reverse=True
    )

    path = os.path.join(MAIN_DIR, "MAIN_TOURNAMENT_SUMMARY.txt")
    with open(path, "w") as f:
        f.write(f"{'='*70}\n")
        f.write(f"  BUILD4GOOD 2026 — MAIN BOT TOURNAMENT SUMMARY\n")
        f.write(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  Main bots: {', '.join(MAIN_BOTS)}\n")
        f.write(f"  Each played vs all {len(BOTS)-1} opponents  |  1000 hands/match\n")
        f.write(f"{'='*70}\n\n")

        f.write(f"  OVERALL RANKING (main bots)\n")
        f.write(f"  {'RANK':<5} {'BOT':<25} {'W-L-T':<10} {'TOTAL CHIPS':>12} {'AVG/HAND':>10}\n")
        f.write(f"  {'-'*65}\n")
        for rank, (bot, r) in enumerate(main_ranked, 1):
            n = len(r["matchups"]) or 1
            total_hands = sum(s["hands_played"] for s in main_stats
                              if s["bot1"] == bot or s["bot2"] == bot) or 1
            wlt = f"{r['wins']}-{r['losses']}-{r['ties']}"
            avg = r["total_chips"] / total_hands
            f.write(f"  {rank:<5} {bot:<25} {wlt:<10} {r['total_chips']:>+12,} {avg:>+10.2f}\n")

        f.write(f"\n{'='*70}\n")
        f.write(f"  WINNER: {main_ranked[0][0]}\n")
        f.write(f"{'='*70}\n\n")

        # Per-main-bot breakdown
        for bot in MAIN_BOTS:
            if bot not in records: continue
            r = records[bot]
            f.write(f"\n  ── {bot} ──\n")
            f.write(f"  {'OPPONENT':<25} {'RESULT':<8} {'CHIPS':>8} {'WIN%':>7} {'AVG/HAND':>10} {'BIGGEST WIN':>12}\n")
            f.write(f"  {'-'*75}\n")
            sorted_m = sorted(r["matchups"], key=lambda x: x["chips"], reverse=True)
            for m in sorted_m:
                f.write(f"  {m['opponent']:<25} {m['result']:<8} {m['chips']:>+8} "
                        f"{m['win_rate']:>6.1f}% {m['avg_per_hand']:>+10.2f} {m['biggest_win']:>12}\n")
            f.write(f"\n  Total chips: {r['total_chips']:+,}  |  "
                    f"Record: {r['wins']}W-{r['losses']}L-{r['ties']}T\n")

    # JSON for further analysis
    with open(os.path.join(MAIN_DIR, "main_results.json"), "w") as f:
        json.dump({
            "date": datetime.now().isoformat(),
            "main_bots": MAIN_BOTS,
            "rankings": [{"rank": i+1, "bot": b, **{k: v for k, v in r.items() if k != "matchups"},
                          "matchups": r["matchups"]} for i, (b, r) in enumerate(main_ranked)],
        }, f, indent=2)

    # Print to console
    print(f"\n{'='*65}")
    print(f"  MAIN BOT RESULTS")
    print(f"{'='*65}")
    print(f"  {'RANK':<5} {'BOT':<25} {'W-L-T':<10} {'TOTAL CHIPS':>12}")
    print(f"  {'-'*55}")
    for rank, (bot, r) in enumerate(main_ranked, 1):
        wlt = f"{r['wins']}-{r['losses']}-{r['ties']}"
        print(f"  {rank:<5} {bot:<25} {wlt:<10} {r['total_chips']:>+12,}")
    print(f"\n  WINNER: {main_ranked[0][0]}")
    print(f"\n  Full stats: {MAIN_DIR}/MAIN_TOURNAMENT_SUMMARY.txt")


def save_other_summary(other_stats):
    if not other_stats:
        return
    bots_seen = set()
    for s in other_stats:
        bots_seen.add(s["bot1"]); bots_seen.add(s["bot2"])
    records = {b: {"wins": 0, "losses": 0, "ties": 0, "total_chips": 0, "matchups": []}
               for b in bots_seen}
    for s in other_stats:
        b1, b2 = s["bot1"], s["bot2"]
        records[b1]["total_chips"] += s["bot1_total"]
        records[b2]["total_chips"] += s["bot2_total"]
        records[b1]["matchups"].append(f"{'W' if s['winner']==b1 else ('T' if s['winner']=='TIE' else 'L')} vs {b2} ({s['bot1_total']:+d})")
        records[b2]["matchups"].append(f"{'W' if s['winner']==b2 else ('T' if s['winner']=='TIE' else 'L')} vs {b1} ({s['bot2_total']:+d})")
        if s["winner"] == b1:
            records[b1]["wins"] += 1; records[b2]["losses"] += 1
        elif s["winner"] == b2:
            records[b2]["wins"] += 1; records[b1]["losses"] += 1
        else:
            records[b1]["ties"] += 1; records[b2]["ties"] += 1

    ranked = sorted(records.items(), key=lambda x: (x[1]["wins"], x[1]["total_chips"]), reverse=True)
    with open(os.path.join(OTHER_DIR, "OTHER_SUMMARY.txt"), "w") as f:
        f.write(f"{'='*65}\n  OTHER BOTS ROUND-ROBIN SUMMARY\n{'='*65}\n\n")
        f.write(f"  {'RANK':<5} {'BOT':<22} {'W-L-T':<10} {'TOTAL CHIPS':>12}\n")
        f.write(f"  {'-'*55}\n")
        for rank, (bot, r) in enumerate(ranked, 1):
            wlt = f"{r['wins']}-{r['losses']}-{r['ties']}"
            f.write(f"  {rank:<5} {bot:<22} {wlt:<10} {r['total_chips']:>+12,}\n")
        f.write(f"\n{'='*65}\n  DETAILED RECORDS\n{'='*65}\n\n")
        for rank, (bot, r) in enumerate(ranked, 1):
            f.write(f"  #{rank} {bot}\n")
            for m in r["matchups"]:
                f.write(f"       {m}\n")
            f.write("\n")


def main():
    other_bots = [b for b in BOTS if b not in MAIN_BOTS]

    # Main matchups: each main bot vs all 11 others (33 total)
    main_matchups = [(m, o) for m in MAIN_BOTS for o in BOTS if o != m]
    # Deduplicate (main vs main counted once)
    seen = set(); deduped_main = []
    for a, b in main_matchups:
        key = tuple(sorted([a, b]))
        if key not in seen:
            seen.add(key); deduped_main.append((a, b))

    # Other matchups: non-main vs non-main
    other_matchups = [(a, b) for a, b in itertools.combinations(other_bots, 2)]

    print(f"Build4Good 2026 — Tournament")
    print(f"Main bots : {MAIN_BOTS}")
    print(f"All bots  : {len(BOTS)}")
    print(f"Main matchups : {len(deduped_main)}  |  Other matchups: {len(other_matchups)}")
    print(f"{'='*65}\n")

    # --- Run main matchups first ---
    print(f">>> MAIN MATCHUPS ({len(deduped_main)})\n")
    main_stats = []
    for i, (b1, b2) in enumerate(deduped_main, 1):
        print(f"[{i}/{len(deduped_main)}]", end=" ")
        try:
            stats = run_match(b1, b2, MAIN_DIR)
            save_matchup_report(stats, MAIN_DIR)
            main_stats.append(stats)
        except subprocess.TimeoutExpired:
            print("TIMEOUT — skipping")
        except Exception as e:
            print(f"ERROR: {e} — skipping")

    save_main_summary(main_stats)

    # --- Run other matchups ---
    if other_matchups:
        print(f"\n>>> OTHER MATCHUPS ({len(other_matchups)})\n")
        other_stats = []
        for i, (b1, b2) in enumerate(other_matchups, 1):
            print(f"[{i}/{len(other_matchups)}]", end=" ")
            try:
                stats = run_match(b1, b2, OTHER_DIR)
                save_matchup_report(stats, OTHER_DIR)
                other_stats.append(stats)
            except subprocess.TimeoutExpired:
                print("TIMEOUT — skipping")
            except Exception as e:
                print(f"ERROR: {e} — skipping")
        save_other_summary(other_stats)

    write_config("rishabh_bot", "check_call_bot")


if __name__ == "__main__":
    main()
