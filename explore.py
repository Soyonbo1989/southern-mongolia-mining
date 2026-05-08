import pandas as pd
from pathlib import Path

src = Path("data/gem-data/Global-Coal-Mine-Tracker-May-2025-V2.xlsx")
df = pd.read_excel(src, sheet_name="GCMT Non-closed Mines")

xl = df[(df["Country / Area"] == "China") &
        (df["State, Province"] == "Inner Mongolia") &
        (df["Prefecture, District"].isin(["Xilin Gol", "Xilingol League"]))]

print(f"Xilingol mines: {len(xl)}\n")

cols = ["Mine Name", "Mine Name (Non-ENG)", "Owners", "Capacity (Mtpa)",
        "Status", "Mine Type", "Latitude", "Longitude"]
print(xl[cols].to_string())
