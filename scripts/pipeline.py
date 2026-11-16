"""Run the whole project from a fresh Spotify export in one command.

Usage: python scripts/pipeline.py "<path to Spotify Account Data folder>"

Steps: clean and combine (prep) -> aggregates and gap check (agg)
       -> Tableau tables (dashboard) -> process images (images)
Then refresh the data source in Tableau and republish.
"""
import subprocess, sys
from pathlib import Path

if len(sys.argv) != 2:
    sys.exit(__doc__)
export = Path(sys.argv[1]).expanduser()
if not list(export.glob("StreamingHistory_music_*.json")):
    sys.exit(f"No StreamingHistory_music_*.json files in {export}")

root = Path(__file__).resolve().parent.parent
scripts, data, images = root / "scripts", root / "data", root / "images"
steps = [
    ("prep", [str(export), str(data)]),
    ("agg", [str(data)]),
    ("dashboard", [str(data)]),
    ("images", [str(data), str(images)]),
]
for name, args in steps:
    print(f"\n== {name}")
    subprocess.run([sys.executable, str(scripts / f"{name}.py"), *args], check=True)
print("\nDone. Next: open the workbook in Tableau, refresh the data source, check the numbers in README.md, republish.")
