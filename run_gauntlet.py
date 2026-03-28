import os
import subprocess
import re

TEST_BOTS = {
    "Passive Bot (No Redraw)": "./test_bots/passive_bot",
    "Calling Station Bot (Random Hole Redraw)": "./test_bots/station_bot",
    "Tight Aggressive Bot (Strategic Redraw)": "./test_bots/tag_bot",
    "Maniac Swapper Bot (Abuses Board Redraw)": "./test_bots/maniac_bot"
}

CONFIG_FILE = "config.py"
LOG_FILE = "results/gamelog.txt"
PYTHON_BIN = r"C:\Users\sapta\Desktop\TACS-PokerBots-2026\.venv\Scripts\python.exe"

def update_config(bot_path, bot_name):
    # Read existing config
    with open(CONFIG_FILE, "r") as f:
        lines = f.readlines()
        
    # Modify lines
    for i, line in enumerate(lines):
        if line.startswith("PLAYER_2_NAME"):
            lines[i] = f'PLAYER_2_NAME = "{bot_name}"\n'
        elif line.startswith("PLAYER_2_PATH"):
            lines[i] = f'PLAYER_2_PATH = "{bot_path}"\n'
            
    # Write back
    with open(CONFIG_FILE, "w") as f:
        f.writelines(lines)

def run_match(bot_name):
    print(f"============================================================")
    print(f">> RUNNING MATCH: ChampionBot vs {bot_name} ...")
    
    # Run the engine
    subprocess.run([PYTHON_BIN, "engine.py"], capture_output=True, text=True)

    # Parse results
    if not os.path.exists(LOG_FILE):
        return "ERROR: Gamelog not found"
        
    with open(LOG_FILE, "r") as f:
        lines = f.readlines()
        
    final_line = ""
    for line in reversed(lines):
        if line.startswith("Final,"):
            final_line = line.strip()
            break
            
    # Count redraws
    champ_redraws = sum(1 for line in lines if "ChampionBot redraws" in line)
    opp_redraws = sum(1 for line in lines if "redraws" in line and "ChampionBot" not in line)
            
    return final_line, champ_redraws, opp_redraws

def main():
    print("\n========= TACS POKERBOTS MONTE CARLO GAUNTLET =========")
    print("Testing ChampionBot against 4 unique opponent archetypes.")
    print("Settings: 1000 Hands per Match | 250 Chips | 2/5 Blinds\n")
    
    results = []
    
    for name, path in TEST_BOTS.items():
        opp_id = name.split(" ")[0]
        update_config(path, opp_id)
        
        final_line, champ_red, opp_red = run_match(name)
        
        # Parse final line: 'Final, ChampionBot (X), Opp (-X)'
        champ_score = 0
        match = re.search(r"ChampionBot \(([-0-9]+)\)", final_line)
        if match:
            champ_score = int(match.group(1))
            
        results.append({
            "opponent": name,
            "score": champ_score,
            "champ_redraws": champ_red,
            "opp_redraws": opp_red
        })
        
        print(f"-> Result: ChampionBot {champ_score:+} chips")
        print(f"   (Redraws used - Champion: {champ_red}, Opponent: {opp_red})\n")
        
    print("================== FINAL GAUNTLET REPORT ==================")
    for r in results:
        status = "WIN" if r["score"] > 0 else "LOSS"
        print(f"{status} | {r['score']:+5d} chips | vs {r['opponent']}")
        print(f"    Redraws Used: Champion={r['champ_redraws']}, Opponent={r['opp_redraws']}")
    print("===========================================================\n")

if __name__ == "__main__":
    main()
