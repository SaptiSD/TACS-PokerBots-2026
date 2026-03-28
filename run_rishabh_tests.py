"""
Runs rishabh_bot vs all 11 opponents, 3 times each.
Results saved to statistics/rishabhstats/
"""

import os
import subprocess
import json
import re
import shutil
from datetime import datetime

OPPONENTS = [
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

RUNS_PER_OPPONENT = 3
OUT_DIR = "statistics/rishabhstats"
CONFIG_FILE = "config.py"
ENGINE_SCRIPT = "engine.py"

os.makedirs(OUT_DIR, exist_ok=True)
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
STARTING_STACK = 250
BIG_BLIND = 5
SMALL_BLIND = 2
PLAYER_TIMEOUT = 180
"""
    with open(CONFIG_FILE, "w") as f:
        f.write(config)


def parse_gamelog(logfile, bot1, bot2):
    stats = {
        "bot1": bot1, "bot2": bot2,
        "bot1_total": 0, "bot2_total": 0,
        "hands_played": 0,
        "bot1_wins": 0, "bot2_wins": 0, "ties": 0,
        "bot1_biggest_win": 0, "bot2_biggest_win": 0,
        "bot1_redraw_count": 0, "bot2_redraw_count": 0,
    }
    if not os.path.exists(logfile):
        return stats
    with open(logfile) as f:
        lines = f.readlines()
    for line in lines:
        line = line.strip()
        m = re.match(rf"^{re.escape(bot1)} awarded (-?\d+)$", line)
        if m:
            delta = int(m.group(1))
            stats["bot1_total"] += delta
            stats["hands_played"] += 1
            if delta > 0:
                stats["bot1_wins"] += 1
                stats["bot1_biggest_win"] = max(stats["bot1_biggest_win"], delta)
            elif delta < 0:
                stats["bot2_wins"] += 1
                stats["bot2_biggest_win"] = max(stats["bot2_biggest_win"], -delta)
            else:
                stats["ties"] += 1
        if "redraws" in line.lower():
            if bot1.lower() in line.lower():
                stats["bot1_redraw_count"] += 1
            elif bot2.lower() in line.lower():
                stats["bot2_redraw_count"] += 1
    stats["bot2_total"] = -stats["bot1_total"]
    stats["winner"] = bot1 if stats["bot1_total"] > 0 else (bot2 if stats["bot1_total"] < 0 else "TIE")
    return stats


def run_match(opponent, run_num):
    print(f"  [{run_num}/3] rishabh_bot vs {opponent} ...", end=" ", flush=True)
    write_config("rishabh_bot", opponent)
    result = subprocess.run(
        ["python3", ENGINE_SCRIPT],
        capture_output=True, text=True, timeout=600
    )
    logfile = "statistics/tmp/gamelog.txt"
    stats = parse_gamelog(logfile, "rishabh_bot", opponent)

    prefix = f"{opponent}_run{run_num}"
    if os.path.exists(logfile):
        shutil.copy(logfile, os.path.join(OUT_DIR, f"{prefix}_gamelog.txt"))
    with open(os.path.join(OUT_DIR, f"{prefix}_engine.log"), "w") as f:
        f.write(result.stdout)
        if result.stderr:
            f.write("\n--- STDERR ---\n" + result.stderr)

    winner_str = f"WINNER: {stats['winner']}"
    print(f"{stats['bot1_total']:+d} chips  →  {winner_str}  (redraws: {stats['bot1_redraw_count']})")
    return stats


def save_summary(all_stats):
    # Aggregate by opponent
    by_opp = {opp: [] for opp in OPPONENTS}
    for s in all_stats:
        by_opp[s["bot2"]].append(s)

    path = os.path.join(OUT_DIR, "RISHABH_STATS_SUMMARY.txt")
    with open(path, "w") as f:
        f.write(f"{'='*70}\n")
        f.write(f"  RISHABH_BOT — Extended Test Results\n")
        f.write(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  {RUNS_PER_OPPONENT} runs x {len(OPPONENTS)} opponents = {RUNS_PER_OPPONENT * len(OPPONENTS)} total matches\n")
        f.write(f"{'='*70}\n\n")

        total_wins = total_losses = total_ties = total_chips = 0

        f.write(f"  {'OPPONENT':<25} {'W-L-T':<10} {'AVG CHIPS':>10} {'MIN':>8} {'MAX':>8} {'AVG REDRAWS':>12}\n")
        f.write(f"  {'-'*75}\n")

        for opp in OPPONENTS:
            runs = by_opp[opp]
            if not runs:
                continue
            wins   = sum(1 for r in runs if r["winner"] == "rishabh_bot")
            losses = sum(1 for r in runs if r["winner"] == opp)
            ties   = sum(1 for r in runs if r["winner"] == "TIE")
            chips  = [r["bot1_total"] for r in runs]
            redraws = [r["bot1_redraw_count"] for r in runs]
            avg_chips = sum(chips) / len(chips)
            avg_redraws = sum(redraws) / len(redraws)
            wlt = f"{wins}-{losses}-{ties}"
            f.write(f"  {opp:<25} {wlt:<10} {avg_chips:>+10.0f} {min(chips):>+8} {max(chips):>+8} {avg_redraws:>12.1f}\n")
            total_wins += wins; total_losses += losses; total_ties += ties
            total_chips += sum(chips)

        f.write(f"\n  {'TOTAL':<25} {total_wins}-{total_losses}-{total_ties:<6} {total_chips:>+10,}\n")
        f.write(f"\n{'='*70}\n")
        f.write(f"  Overall record: {total_wins}W-{total_losses}L-{total_ties}T  |  Total chips: {total_chips:+,}\n")
        f.write(f"{'='*70}\n")

    # Also print to console
    print(f"\n{'='*65}")
    print(f"  RISHABH_BOT SUMMARY  ({total_wins}W-{total_losses}L-{total_ties}T  |  {total_chips:+,} chips)")
    print(f"{'='*65}")
    print(f"  Full stats: {path}")


def main():
    print(f"rishabh_bot extended tests — {RUNS_PER_OPPONENT} runs x {len(OPPONENTS)} opponents")
    print(f"Output: {OUT_DIR}/\n")

    all_stats = []
    for opp in OPPONENTS:
        print(f"\n>> vs {opp}")
        for run_num in range(1, RUNS_PER_OPPONENT + 1):
            try:
                stats = run_match(opp, run_num)
                all_stats.append(stats)
            except subprocess.TimeoutExpired:
                print("TIMEOUT")
            except Exception as e:
                print(f"ERROR: {e}")

    save_summary(all_stats)
    write_config("rishabh_bot", "check_call_bot")


if __name__ == "__main__":
    main()
